import json
import subprocess
import os
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO
import datetime

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# To store the background task state
background_task_started = False
# State for the monitor task
keynote_state = {
    "document_open": False,
    "is_playing": False,
    "last_slide_number": -1,
    "document_name": None
}

def get_keynote_status():
    """Helper function to get current Keynote status using a single AppleScript call."""
    script = '''
    tell application "Keynote"
        if not (exists front document) then
            return "closed"
        end if
        
        tell front document
            set doc_name to its name
            set slide_num to slide number of its current slide
            set is_playing to playing of application "Keynote"
            
            return doc_name & "||" & slide_num & "||" & is_playing
        end tell
    end tell
    '''
    try:
        result = subprocess.run(['osascript', '-e', script], check=True, capture_output=True, text=True)
        output = result.stdout.strip()

        if output == "closed":
            return {"document_open": False, "is_playing": False, "slide_number": None, "document_name": None}
        
        parts = output.split("||")
        if len(parts) < 3:
            # Handle cases where the output might not be as expected
            return {"document_open": False, "is_playing": False, "slide_number": None, "document_name": None}

        doc_name, slide_num_str, is_playing_str = parts[0], parts[1], parts[2]
        slide_num = int(slide_num_str)
        is_playing = is_playing_str == 'true'
        
        return {"document_open": True, "is_playing": is_playing, "slide_number": slide_num, "document_name": doc_name}
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        # Keynote not open, or some other error. Treat as closed.
        return {"document_open": False, "is_playing": False, "slide_number": None, "document_name": None}

def monitor_keynote_slides():
    """A background task that checks for Keynote state changes and emits updates."""
    global keynote_state
    
    # Initialize state on first run
    status = get_keynote_status()
    keynote_state = {
        "document_open": status["document_open"],
        "is_playing": status["is_playing"],
        "last_slide_number": status["slide_number"],
        "document_name": status["document_name"]
    }

    while True:
        status = get_keynote_status()
        
        # Check if document was closed
        if keynote_state["document_open"] and not status["document_open"]:
            print("Keynote presentation closed.")
            socketio.emit('presentation_closed')
            
        # Check if presentation was stopped (exited slideshow mode)
        elif keynote_state["document_open"] and status["document_open"] and keynote_state["is_playing"] and not status["is_playing"]:
            print("Keynote presentation stopped.")
            socketio.emit('presentation_stopped')

        # Check if presentation was started (entered play mode)
        elif keynote_state["document_open"] and status["document_open"] and not keynote_state["is_playing"] and status["is_playing"]:
            print("Keynote presentation started.")
            socketio.emit('presentation_started')

        # Check for slide change
        elif status["document_open"] and status["slide_number"] != keynote_state["last_slide_number"]:
            print(f"Slide changed from {keynote_state['last_slide_number']} to {status['slide_number']}")
            socketio.emit('slide_update', {'slide_number': status['slide_number']})

        # Update state for next iteration
        keynote_state = {
            "document_open": status["document_open"],
            "is_playing": status["is_playing"],
            "last_slide_number": status["slide_number"],
            "document_name": status["document_name"]
        }
        
        socketio.sleep(1) # Poll every second, as state changes are less frequent than slide advances

# Route to serve the main HTML file
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# Route to serve static files (CSS, JS, images)
@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

@socketio.on('connect')
def handle_connect():
    global background_task_started
    if not background_task_started:
        socketio.start_background_task(target=monitor_keynote_slides)
        background_task_started = True
        print('Client connected, starting Keynote monitoring.')
    else:
        print('Client connected.')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

# API endpoint to list Keynote presentations in the current directory
@app.route('/api/list_presentations', methods=['GET'])
def list_presentations():
    try:
        project_root = os.path.expanduser('~')
        req_path = request.args.get('path', '.')

        # Security: Prevent path traversal
        current_path = os.path.abspath(os.path.join(project_root, req_path))
        if not current_path.startswith(project_root):
            return jsonify({"status": "error", "message": "Access denied."}), 403

        # Get relative path for response
        relative_path = os.path.relpath(current_path, project_root)
        if relative_path == '.':
            relative_path = ''

        items = []
        with os.scandir(current_path) as it:
            for entry in it:
                if entry.name.startswith('.'):
                    continue
                
                entry_path = os.path.join(relative_path, entry.name).replace(os.path.sep, '/')
                if entry.is_dir():
                    items.append({'name': entry.name, 'type': 'directory', 'path': entry_path})
                elif entry.is_file() and entry.name.endswith('.key'):
                    items.append({'name': entry.name, 'type': 'file', 'path': entry_path})
        
        # Sort folders first, then files, all alphabetically
        items.sort(key=lambda x: (x['type'] != 'directory', x['name'].lower()))
        
        return jsonify({
            "status": "success",
            "path": relative_path,
            "items": items
        })
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "Directory not found."}), 404
    except Exception as e:
        print(f"Error listing presentations: {e}")
        return jsonify({"status": "error", "message": "An internal error occurred."}), 500

# API endpoint to open a Keynote presentation
@app.route('/api/open_presentation', methods=['POST'])
def open_presentation():
    data = request.get_json()
    filename = data.get('filename')

    if not filename:
        return jsonify({"status": "error", "message": "Filename not provided."}), 400

    # Security check to prevent path traversal
    project_root = os.path.expanduser('~') # Start from user's home directory
    
    # Ensure the provided filename is a relative path
    if os.path.isabs(filename):
        return jsonify({"status": "error", "message": "Invalid filename. Absolute paths are not allowed."}), 400

    file_path = os.path.abspath(os.path.join(project_root, filename))
    
    if not file_path.startswith(project_root):
        return jsonify({"status": "error", "message": "Invalid filename. Path traversal attempt detected."}), 400
    
    # Check if file exists to avoid errors
    if not os.path.isfile(file_path):
        return jsonify({"status": "error", "message": f"File '{filename}' not found."}), 404

    try:
        # Step 1: Open the presentation
        open_script = f'''
        tell application "Keynote"
            open "{file_path}"
            activate
        end tell
        '''
        subprocess.run(['osascript', '-e', open_script], check=True, capture_output=True, text=True)

        # Step 2: Get the slide count of the newly opened presentation
        count_script = 'tell application "Keynote" to get count of slides of the front document'
        result = subprocess.run(['osascript', '-e', count_script], check=True, capture_output=True, text=True)
        slide_count = int(result.stdout.strip())

        # Step 3: Update slide_timings.json
        timings_path = 'static/slide_timings.json'
        with open(timings_path, 'r+') as f:
            timings_data = json.load(f)
            
            # Use the relative filename as the presentation ID
            presentation_id = filename
            
            # If the presentation is not already in the file, add it.
            if presentation_id not in timings_data.get('presentations', {}):
                timings_data['presentations'][presentation_id] = {
                    "name": os.path.basename(filename),
                    "slides": [{"slide": i, "estimated_time_seconds": 60, "actual_time_seconds": None} for i in range(1, slide_count + 1)]
                }
            
            # Update the current presentation ID
            timings_data['current_presentation_id'] = presentation_id
            
            # Go to the beginning of the file to overwrite
            f.seek(0)
            json.dump(timings_data, f, indent=2)
            f.truncate()

        # Step 4: Get the current slide number
        current_slide_script = 'tell application "Keynote" to get slide number of the current slide of the front document'
        try:
            result = subprocess.run(['osascript', '-e', current_slide_script], check=True, capture_output=True, text=True)
            current_slide_number = int(result.stdout.strip())
        except Exception:
            current_slide_number = 1  # Fallback to 1 if unable to get

        return jsonify({
            "status": "success",
            "message": f"Presentation '{filename}' opened and configured successfully.",
            "current_slide_number": current_slide_number
        })

    except subprocess.CalledProcessError as e:
        # This can happen if Keynote is not installed or another issue occurs.
        return jsonify({"status": "error", "message": f"Failed to open or get info from presentation. Is Keynote installed? Error: {e.stderr.strip()}"}), 500
    except FileNotFoundError:
        # This error occurs if 'osascript' is not found (not on macOS).
        return jsonify({"status": "error", "message": "This feature is only available on macOS."}), 501
    except (ValueError, json.JSONDecodeError) as e:
        print(f"Error processing data for presentation: {e}")
        return jsonify({"status": "error", "message": f"Could not process presentation data. Error: {e}"}), 500
    except Exception as e:
        print(f"Error opening presentation: {e}")
        return jsonify({"status": "error", "message": "An internal error occurred."}), 500

# API endpoint to save slide timings
@app.route('/api/save_timings', methods=['POST'])
def save_timings():
    try:
        data = request.get_json()
        # Basic validation
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid data format. Expected a dictionary."}), 400
        
        with open('static/slide_timings.json', 'w') as f:
            json.dump(data, f, indent=2)
            
        return jsonify({"status": "success", "message": "Timings saved successfully."})
    except Exception as e:
        # Log the error for debugging
        print(f"Error saving timings: {e}")
        return jsonify({"status": "error", "message": "An internal error occurred."}), 500

# API endpoint to start Keynote presentation
@app.route('/api/start_presentation', methods=['POST'])
def start_presentation():
    try:
        # This AppleScript command tells Keynote to start the slideshow of the frontmost document.
        script = 'tell application "Keynote" to start slideshow of the front document'
        subprocess.run(['osascript', '-e', script], check=True, capture_output=True, text=True)
        return jsonify({"status": "success", "message": "Presentation started successfully."})
    except subprocess.CalledProcessError as e:
        # This error is triggered if the AppleScript returns a non-zero exit code,
        # for example, if Keynote is not open or no presentation is loaded.
        return jsonify({"status": "error", "message": f"Failed to start presentation. Is Keynote open with a presentation loaded? Error: {e.stderr.strip()}"}), 500
    except FileNotFoundError:
        # This error occurs if 'osascript' is not found, which means the OS is not macOS.
        return jsonify({"status": "error", "message": "This feature is only available on macOS."}), 501
    except Exception as e:
        # General catch-all for other unexpected errors.
        print(f"Error starting presentation: {e}")
        return jsonify({"status": "error", "message": "An internal error occurred."}), 500

# API endpoint to stop Keynote presentation
@app.route('/api/stop_presentation', methods=['POST'])
def stop_presentation():
    try:
        # This AppleScript command tells Keynote to stop the current slideshow.
        script = 'tell application "Keynote" to stop slideshow'
        subprocess.run(['osascript', '-e', script], check=True, capture_output=True, text=True)
        return jsonify({"status": "success", "message": "Presentation stopped successfully."})
    except subprocess.CalledProcessError as e:
        # This error can occur if there is no slideshow currently running. It's safe to ignore.
        return jsonify({"status": "success", "message": "Presentation already stopped or no slideshow running."})
    except FileNotFoundError:
        # This error occurs if 'osascript' is not found, which means the OS is not macOS.
        return jsonify({"status": "error", "message": "This feature is only available on macOS."}), 501
    except Exception as e:
        # General catch-all for other unexpected errors.
        print(f"Error stopping presentation: {e}")
        return jsonify({"status": "error", "message": "An internal error occurred."}), 500

# API endpoint to close Keynote presentation
@app.route('/api/close_presentation', methods=['POST'])
def close_presentation():
    try:
        # Save elapsed times before closing the presentation
        elapsed_dir = os.path.join('static', 'elapsed_times')
        os.makedirs(elapsed_dir, exist_ok=True)
        
        timings_path = os.path.join('static', 'slide_timings.json')
        with open(timings_path, 'r+') as f:
            timings_data = json.load(f)
            presentation_id = timings_data.get('current_presentation_id')

            if presentation_id and presentation_id in timings_data.get('presentations', {}):
                # Save the final timings
                export_data = timings_data['presentations'][presentation_id]
                base_name = os.path.splitext(os.path.basename(presentation_id))[0]
                timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                out_path = os.path.join(elapsed_dir, f'{base_name}_elapsed_{timestamp}.json')
                with open(out_path, 'w') as outf:
                    json.dump(export_data, outf, indent=2)

            # Reset the current presentation ID
            timings_data['current_presentation_id'] = None
            f.seek(0)
            json.dump(timings_data, f, indent=2)
            f.truncate()

        # Now close the Keynote document
        script = 'tell application "Keynote" to close front document'
        subprocess.run(['osascript', '-e', script], check=True, capture_output=True, text=True)
        return jsonify({"status": "success", "message": "Presentation closed successfully."})
    except subprocess.CalledProcessError:
        # This can happen if no document is open, which is a success from our perspective.
        return jsonify({"status": "success", "message": "No presentation was open."})
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "This feature is only available on macOS."}), 501
    except Exception as e:
        print(f"Error closing presentation: {e}")
        return jsonify({"status": "error", "message": "An internal error occurred."}), 500

# API endpoint to advance to the next slide
@app.route('/api/next_slide', methods=['POST'])
def next_slide():
    try:
        # This AppleScript command advances the slide and returns the new slide number.
        script = """
        tell application "Keynote"
            if playing is true then
                show next
            else
                if not (exists front document) then error "No presentation open."
                tell front document
                    set current_slide_number to get slide number of current slide
                    if current_slide_number < (count of slides) then
                        set current slide to slide (current_slide_number + 1)
                    end if
                end tell
            end if
            return get slide number of the current slide of the front document
        end tell
        """
        result = subprocess.run(['osascript', '-e', script], check=True, capture_output=True, text=True)
        slide_number = int(result.stdout.strip())
        return jsonify({"status": "success", "message": "Moved to next slide.", "slide_number": slide_number})
    except subprocess.CalledProcessError as e:
        # This error can occur if Keynote is not open or no presentation is loaded.
        return jsonify({"status": "error", "message": f"Failed to move to next slide. Is a presentation open? Error: {e.stderr.strip()}"}), 500
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "This feature is only available on macOS."}), 501
    except ValueError:
        return jsonify({"status": "error", "message": "Failed to parse slide number from Keynote."}), 500
    except Exception as e:
        print(f"Error moving to next slide: {e}")
        return jsonify({"status": "error", "message": "An internal error occurred."}), 500

# API endpoint to go to the previous slide
@app.route('/api/previous_slide', methods=['POST'])
def previous_slide():
    try:
        # This AppleScript command goes to the previous slide and returns the new slide number.
        script = """
        tell application "Keynote"
            if playing is true then
                show previous
            else
                if not (exists front document) then error "No presentation open."
                tell front document
                    set current_slide_number to get slide number of current slide
                    if current_slide_number > 1 then
                        set current slide to slide (current_slide_number - 1)
                    end if
                end tell
            end if
            return get slide number of the current slide of the front document
        end tell
        """
        result = subprocess.run(['osascript', '-e', script], check=True, capture_output=True, text=True)
        slide_number = int(result.stdout.strip())
        return jsonify({"status": "success", "message": "Moved to previous slide.", "slide_number": slide_number})
    except subprocess.CalledProcessError as e:
        # This error can occur if Keynote is not open or no presentation is loaded.
        return jsonify({"status": "error", "message": f"Failed to move to previous slide. Is a presentation open? Error: {e.stderr.strip()}"}), 500
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "This feature is only available on macOS."}), 501
    except ValueError:
        return jsonify({"status": "error", "message": "Failed to parse slide number from Keynote."}), 500
    except Exception as e:
        print(f"Error moving to previous slide: {e}")
        return jsonify({"status": "error", "message": "An internal error occurred."}), 500

# API endpoint to get the current slide number
@app.route('/api/current_slide_number', methods=['GET'])
def get_current_slide_number():
    try:
        # This AppleScript gets the slide number of the currently visible slide in the frontmost presentation.
        script = 'tell application "Keynote" to get slide number of the current slide of the front document'
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
        
        if result.returncode != 0:
            # This can happen if Keynote is not open or no presentation is loaded.
            # It's not a server error, but a state where no slide is active.
            return jsonify({"status": "success", "slide_number": None, "message": "No active presentation in Keynote."})

        slide_number = int(result.stdout.strip())
        return jsonify({"status": "success", "slide_number": slide_number})
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "This feature is only available on macOS."}), 501
    except ValueError:
        return jsonify({"status": "error", "message": "Failed to parse slide number from Keynote."}), 500
    except Exception as e:
        print(f"Error getting slide number: {e}")
        return jsonify({"status": "error", "message": "An internal error occurred."}), 500

# API endpoint to go to a specific slide
@app.route('/api/goto_slide/<int:slide_number>', methods=['POST'])
def goto_slide(slide_number):
    try:
        # This AppleScript command tells Keynote to go to a specific slide number,
        # handling both presentation and edit modes.
        script = f'''
        tell application "Keynote"
            if not (exists front document) then error "No presentation open."
            
            if playing is true then
                show slide {slide_number} of the front document
            else
                set current slide of front document to slide {slide_number} of front document
            end if

            return get slide number of the current slide of the front document
        end tell
        '''
        result = subprocess.run(['osascript', '-e', script], check=True, capture_output=True, text=True)
        new_slide_number = int(result.stdout.strip())
        return jsonify({"status": "success", "message": f"Moved to slide {new_slide_number}.", "slide_number": new_slide_number})
    except (subprocess.CalledProcessError, ValueError) as e:
        error_message = e.stderr.strip() if isinstance(e, subprocess.CalledProcessError) else str(e)
        # This error can occur if there is no slideshow running or the slide number is invalid.
        return jsonify({"status": "error", "message": f"Failed to move to slide {slide_number}. Is a presentation open and the slide number valid? Error: {error_message}"}), 500
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "This feature is only available on macOS."}), 501
    except Exception as e:
        print(f"Error moving to slide {slide_number}: {e}")
        return jsonify({"status": "error", "message": "An internal error occurred."}), 500

# API endpoint to get the total number of slides
@app.route('/api/slide_count', methods=['GET'])
def get_slide_count():
    try:
        # This AppleScript gets the total number of slides in the frontmost presentation.
        script = 'tell application "Keynote" to get count of slides of the front document'
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)

        if result.returncode != 0:
            return jsonify({"status": "success", "slide_count": 0, "message": "No active presentation in Keynote."})

        slide_count = int(result.stdout.strip())
        return jsonify({"status": "success", "slide_count": slide_count})
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "This feature is only available on macOS."}), 501
    except ValueError:
        return jsonify({"status": "error", "message": "Failed to parse slide count from Keynote."}), 500
    except Exception as e:
        print(f"Error getting slide count: {e}")
        return jsonify({"status": "error", "message": "An internal error occurred."}), 500

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5002) 