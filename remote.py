from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import subprocess
import os
import threading
import time
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'keynote-remote-secret-key'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state for slide tracking
slide_monitor = {
    'active': False,
    'current_slide': None,
    'total_slides': None,
    'last_check': None,
    'thread': None,
    'interval': 2.0,  # Check every 2 seconds
    # New slide timer functionality
    'slide_timer_start': None,  # When current slide started
    'slide_timers': {},  # Dict to track time spent on each slide: {slide_number: total_seconds}
    'presentation_running': False,  # Track if presentation is actually running
    'presentation_start_time': None,  # When the entire presentation started
    # Custom slide timing functionality
    'planned_timings': {},  # Dict to store planned time for each slide: {slide_number: seconds}
    'timing_file_path': None,  # Path to the timing file
    'keynote_document_path': None  # Path to the current Keynote document
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/index')
def index_page():
    return render_template('index.html')

@app.route('/test')
def test_interface():
    return render_template('test.html')

@app.route('/debug_timing')
def debug_timing_interface():
    return render_template('debug_timing.html')

@app.route('/open-presentation')
def open_presentation():
    return render_template('open-presentation.html')

# Function to run AppleScript/JXA
def run_applescript(script_code):
    try:
        # Use osascript to execute the AppleScript/JXA
        # The -l JavaScript flag tells osascript to interpret as JXA
        # For AppleScript, omit -l JavaScript
        result = subprocess.run(['osascript', '-e', script_code],
                                capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Error executing script: {e.stderr}"
    except Exception as e:
        return f"An unexpected error occurred: {e}"

def get_slide_number_internal():
    """Internal function to get slide number without JSON formatting"""
    script = """
    tell application "Keynote"
        if exists front document then
            set currentSlideObj to current slide of front document
            set slideNumber to slide number of currentSlideObj
            return slideNumber as string
        else
            return "ERROR: No Keynote document open."
        end if
    end tell
    """
    
    script_output = run_applescript(script)
    
    # Check for errors
    if script_output.startswith("ERROR:") or "No Keynote document open" in script_output or "Error executing script:" in script_output:
        return None
    
    try:
        return int(script_output.strip())
    except ValueError:
        return None

def get_total_slides_internal():
    """Internal function to get total number of slides without JSON formatting"""
    script = """
    tell application "Keynote"
        if exists front document then
            set slideCount to count of slides of front document
            return slideCount as string
        else
            return "ERROR: No Keynote document open."
        end if
    end tell
    """
    
    script_output = run_applescript(script)
    
    # Check for errors
    if script_output.startswith("ERROR:") or "No Keynote document open" in script_output or "Error executing script:" in script_output:
        return None
    
    try:
        return int(script_output.strip())
    except ValueError:
        return None

def get_keynote_document_path():
    """Get the file path of the current Keynote document"""
    script = """
    tell application "Keynote"
        if exists front document then
            try
                set docPath to file of front document
                return POSIX path of docPath
            on error
                return "ERROR: Document has no file path (may be imported PowerPoint - please save as Keynote file first)."
            end try
        else
            return "ERROR: No Keynote document open."
        end if
    end tell
    """
    
    script_output = run_applescript(script)
    
    # Check for errors
    if script_output.startswith("ERROR:") or "No Keynote document open" in script_output or "Error executing script:" in script_output:
        return None
    
    return script_output.strip()

def create_timing_json_structure(presentation_name, total_slides, planned_time_per_slide=60):
    """Create a structured JSON timing file format"""
    import datetime
    
    current_time = datetime.datetime.now().isoformat() + 'Z'
    
    slide_timings = {}
    for slide_num in range(1, total_slides + 1):
        slide_timings[str(slide_num)] = {
            "plannedTime": planned_time_per_slide,
            "notes": "",
            "description": f"Slide {slide_num}",
            "importance": "normal"  # normal, high, low
        }
    
    total_planned_time = total_slides * planned_time_per_slide
    
    return {
        "version": "1.0",
        "formatType": "keynote-timing",
        "presentationInfo": {
            "name": presentation_name,
            "totalSlides": total_slides,
            "createdAt": current_time,
            "lastModified": current_time
        },
        "defaultTimings": {
            "defaultSlideTime": planned_time_per_slide,
            "transitionTime": 2  # seconds between slides
        },
        "slideTimings": slide_timings,
        "metadata": {
            "totalPlannedTime": total_planned_time,
            "estimatedDuration": f"{total_planned_time // 60}m {total_planned_time % 60}s",
            "slidesWithCustomTiming": 0,
            "averageTimePerSlide": planned_time_per_slide
        }
    }

def migrate_txt_to_json(txt_file_path, json_file_path, presentation_name, total_slides):
    """Migrate old .txt timing file to new .json format"""
    try:
        if not os.path.exists(txt_file_path):
            return False
        
        print(f"🔄 Migrating old timing file: {txt_file_path}")
        
        # Parse old txt format
        old_timings = {}
        with open(txt_file_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                try:
                    parts = line.split(',')
                    if len(parts) >= 2:
                        slide_number = int(parts[0].strip())
                        timing_seconds = float(parts[1].strip())
                        old_timings[slide_number] = timing_seconds
                except ValueError:
                    continue
        
        # Create new JSON structure
        json_data = create_timing_json_structure(presentation_name, total_slides)
        
        # Update with old timing data
        custom_timing_count = 0
        total_planned_time = 0
        
        for slide_num in range(1, total_slides + 1):
            if slide_num in old_timings:
                planned_time = old_timings[slide_num]
                if planned_time != 60:  # Non-default timing
                    custom_timing_count += 1
            else:
                planned_time = 60  # Default
            
            json_data["slideTimings"][str(slide_num)]["plannedTime"] = planned_time
            total_planned_time += planned_time
        
        # Update metadata
        json_data["metadata"]["totalPlannedTime"] = total_planned_time
        json_data["metadata"]["estimatedDuration"] = f"{total_planned_time // 60}m {total_planned_time % 60}s"
        json_data["metadata"]["slidesWithCustomTiming"] = custom_timing_count
        json_data["metadata"]["averageTimePerSlide"] = total_planned_time / total_slides if total_slides > 0 else 0
        
        # Save JSON file
        with open(json_file_path, 'w') as f:
            json.dump(json_data, f, indent=2)
        
        # Backup old file
        backup_path = txt_file_path + '.backup'
        os.rename(txt_file_path, backup_path)
        
        print(f"✅ Migrated timing file to JSON format: {json_file_path}")
        print(f"📦 Backed up old file to: {backup_path}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error migrating timing file: {e}")
        return False

def save_powerpoint_as_keynote(original_path):
    """Save the current PowerPoint document as a Keynote file"""
    try:
        # Generate new Keynote file path (same directory, same name, .key extension)
        base_path = os.path.splitext(original_path)[0]
        keynote_path = base_path + '.key'
        
        # Check if Keynote file already exists
        if os.path.exists(keynote_path):
            print(f"ℹ️  Keynote file already exists: {keynote_path}")
            return keynote_path
        
        print(f"💾 Saving PowerPoint as Keynote file: {keynote_path}")
        
        script = f'''
        tell application "Keynote"
            if exists front document then
                try
                    save front document in POSIX file "{keynote_path}"
                    return "SUCCESS: Saved as {os.path.basename(keynote_path)}"
                on error errMsg
                    return "ERROR: " & errMsg
                end try
            else
                return "ERROR: No document to save"
            end if
        end tell
        '''
        
        script_output = run_applescript(script)
        
        if script_output.startswith("ERROR:"):
            print(f"❌ Error saving as Keynote: {script_output}")
            return None
        
        if os.path.exists(keynote_path):
            print(f"✅ Successfully saved PowerPoint as Keynote: {keynote_path}")
            return keynote_path
        else:
            print(f"❌ Keynote file was not created: {keynote_path}")
            return None
            
    except Exception as e:
        print(f"❌ Exception saving PowerPoint as Keynote: {e}")
        return None

def auto_convert_powerpoint_to_keynote(original_powerpoint_path=None):
    """Check if current document is a PowerPoint import and auto-convert to Keynote"""
    try:
        # First check if we can get a document path
        current_path = get_keynote_document_path()
        
        if current_path:
            # We have a valid path, check if it's a PowerPoint file
            file_ext = os.path.splitext(current_path.lower())[1]
            if file_ext in ['.ppt', '.pptx']:
                print(f"🔄 Detected PowerPoint file: {current_path}")
                return save_powerpoint_as_keynote(current_path)
            else:
                # Already a Keynote file
                return current_path
        else:
            # No file path - might be an unsaved PowerPoint import
            print("🔍 No file path detected - checking if document exists...")
            
            # Check if there's a document open without a file path
            script = """
            tell application "Keynote"
                if exists front document then
                    try
                        set docName to name of front document
                        return "UNTITLED:" & docName
                    on error
                        return "ERROR: Cannot get document name"
                    end try
                else
                    return "ERROR: No document open"
                end if
            end tell
            """
            
            script_output = run_applescript(script)
            
            if script_output.startswith("UNTITLED:"):
                doc_name = script_output.replace("UNTITLED:", "").strip()
                print(f"📄 Found untitled document: {doc_name}")
                
                # If we have the original PowerPoint path, use its directory
                if original_powerpoint_path and os.path.exists(original_powerpoint_path):
                    target_directory = os.path.dirname(original_powerpoint_path)
                    base_name = os.path.splitext(os.path.basename(original_powerpoint_path))[0]
                    print(f"📁 Using original PowerPoint directory: {target_directory}")
                else:
                    # Fall back to Documents folder
                    target_directory = os.path.expanduser("~/Documents")
                    # Clean up the document name for file system
                    base_name = "".join(c for c in doc_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
                    if not base_name:
                        base_name = "Converted_Presentation"
                    print(f"⚠️  No original path provided, using Documents folder: {target_directory}")
                
                keynote_path = os.path.join(target_directory, base_name + '.key')
                
                # Make sure we don't overwrite existing files
                counter = 1
                original_keynote_path = keynote_path
                while os.path.exists(keynote_path):
                    keynote_path = os.path.join(target_directory, f"{base_name}_{counter}.key")
                    counter += 1
                
                print(f"💾 Auto-saving imported PowerPoint to: {keynote_path}")
                
                script = f'''
                tell application "Keynote"
                    if exists front document then
                        try
                            save front document in POSIX file "{keynote_path}"
                            return "SUCCESS: Auto-saved as {os.path.basename(keynote_path)}"
                        on error errMsg
                            return "ERROR: " & errMsg
                        end try
                    else
                        return "ERROR: No document to save"
                    end if
                end tell
                '''
                
                script_output = run_applescript(script)
                
                if script_output.startswith("ERROR:"):
                    print(f"❌ Error auto-saving: {script_output}")
                    return None
                
                if os.path.exists(keynote_path):
                    print(f"✅ Successfully auto-saved PowerPoint as: {keynote_path}")
                    return keynote_path
                else:
                    print(f"❌ Auto-save failed: {keynote_path}")
                    return None
            
        return None
        
    except Exception as e:
        print(f"❌ Exception in auto_convert_powerpoint_to_keynote: {e}")
        return None

def load_slide_timings(original_powerpoint_path=None):
    """Load planned slide timings from the timing file (JSON format with .txt migration)"""
    try:
        # Try to auto-convert PowerPoint to Keynote if needed
        keynote_path = auto_convert_powerpoint_to_keynote(original_powerpoint_path)
        if not keynote_path:
            print("⚠️  No Keynote document available, cannot load timing file")
            return False
        
        # Store the document path
        slide_monitor['keynote_document_path'] = keynote_path
        
        # Generate timing file paths
        base_path = os.path.splitext(keynote_path)[0]
        json_timing_file_path = base_path + '.json'
        txt_timing_file_path = base_path + '.txt'
        
        slide_monitor['timing_file_path'] = json_timing_file_path
        
        # Get presentation info
        presentation_name = os.path.basename(base_path)
        total_slides = get_total_slides_internal()
        
        if total_slides is None or total_slides <= 0:
            print("⚠️  Could not determine total slides, cannot load timing file")
            slide_monitor['planned_timings'] = {}
            return False
        
        # Check for existing files and migration
        json_exists = os.path.exists(json_timing_file_path)
        txt_exists = os.path.exists(txt_timing_file_path)
        
        if not json_exists and txt_exists:
            # Migrate old .txt format to new .json format
            print(f"🔄 Found old .txt timing file, migrating to JSON format...")
            if migrate_txt_to_json(txt_timing_file_path, json_timing_file_path, presentation_name, total_slides):
                json_exists = True
        
        if not json_exists:
            # Create new default JSON timing file
            print(f"📝 Creating default JSON timing file with {total_slides} slides at 1 minute each...")
            
            try:
                json_data = create_timing_json_structure(presentation_name, total_slides, 60)
                
                with open(json_timing_file_path, 'w') as f:
                    json.dump(json_data, f, indent=2)
                
                print(f"✅ Created default JSON timing file: {json_timing_file_path}")
                
            except Exception as e:
                print(f"❌ Error creating default JSON timing file: {e}")
                slide_monitor['planned_timings'] = {}
                return False
        
        # Load JSON timing file
        try:
            with open(json_timing_file_path, 'r') as f:
                timing_data = json.load(f)
            
            # Validate JSON structure
            if not isinstance(timing_data, dict) or 'slideTimings' not in timing_data:
                print(f"❌ Invalid JSON timing file format: {json_timing_file_path}")
                slide_monitor['planned_timings'] = {}
                return False
            
            # Extract slide timings
            planned_timings = {}
            slide_timings = timing_data.get('slideTimings', {})
            
            for slide_str, slide_data in slide_timings.items():
                try:
                    slide_number = int(slide_str)
                    if isinstance(slide_data, dict) and 'plannedTime' in slide_data:
                        planned_time = float(slide_data['plannedTime'])
                        if planned_time >= 0:
                            planned_timings[slide_number] = planned_time
                        else:
                            print(f"⚠️  Invalid planned time for slide {slide_number}: {planned_time}")
                    else:
                        print(f"⚠️  Invalid slide data for slide {slide_number}")
                except (ValueError, TypeError) as e:
                    print(f"⚠️  Error parsing slide {slide_str}: {e}")
                    continue
            
            # Store the planned timings and metadata
            slide_monitor['planned_timings'] = planned_timings
            slide_monitor['timing_metadata'] = timing_data.get('metadata', {})
            slide_monitor['presentation_info'] = timing_data.get('presentationInfo', {})
            
            total_planned_time = timing_data.get('metadata', {}).get('totalPlannedTime', sum(planned_timings.values()))
            slides_with_custom_timing = timing_data.get('metadata', {}).get('slidesWithCustomTiming', 0)
            
            print(f"✅ Loaded JSON timing for {len(planned_timings)} slides from: {json_timing_file_path}")
            print(f"📊 Total planned time: {total_planned_time/60:.1f} minutes ({slides_with_custom_timing} custom timings)")
            
            return True
            
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing JSON timing file: {e}")
            slide_monitor['planned_timings'] = {}
            return False
        except Exception as e:
            print(f"❌ Error loading JSON timing file: {e}")
            slide_monitor['planned_timings'] = {}
            return False
        
    except Exception as e:
        print(f"❌ Error loading slide timings: {e}")
        slide_monitor['planned_timings'] = {}
        return False

def get_slide_timing_status(slide_number, current_elapsed_time=None):
    """Get timing status for a specific slide"""
    if slide_number not in slide_monitor['planned_timings']:
        return {
            'hasPlannedTime': False,
            'plannedTime': None,
            'actualTime': current_elapsed_time,
            'status': 'no_timing',
            'variance': None,
            'percentageUsed': None
        }
    
    planned_time = slide_monitor['planned_timings'][slide_number]
    actual_time = current_elapsed_time if current_elapsed_time is not None else 0
    
    # Calculate status
    if actual_time <= planned_time * 0.9:  # Within 90% of planned time
        status = 'on_time'
    elif actual_time <= planned_time:  # Within planned time but over 90%
        status = 'warning'
    else:  # Over planned time
        status = 'over_time'
    
    variance = actual_time - planned_time
    percentage_used = (actual_time / planned_time * 100) if planned_time > 0 else 0
    
    return {
        'hasPlannedTime': True,
        'plannedTime': planned_time,
        'actualTime': actual_time,
        'status': status,
        'variance': variance,
        'percentageUsed': percentage_used
    }

def slide_monitor_worker():
    """Background worker that monitors slide changes"""
    print("🔍 Starting slide monitor...")
    
    while slide_monitor['active']:
        try:
            current_slide = get_slide_number_internal()
            total_slides = get_total_slides_internal()
            
            # Check if presentation was closed (both current_slide and total_slides are None)
            if current_slide is None and total_slides is None:
                # Check if we previously had a presentation open
                if (slide_monitor['current_slide'] is not None or 
                    slide_monitor['total_slides'] is not None or 
                    slide_monitor['presentation_running']):
                    
                    print("📄 Presentation file closed - resetting timing state")
                    
                    # Reset all timing state
                    slide_monitor['current_slide'] = None
                    slide_monitor['total_slides'] = None
                    slide_monitor['presentation_running'] = False
                    slide_monitor['slide_timer_start'] = None
                    slide_monitor['presentation_start_time'] = None
                    slide_monitor['slide_timers'] = {}
                    slide_monitor['planned_timings'] = {}
                    slide_monitor['timing_file_path'] = None
                    slide_monitor['keynote_document_path'] = None
                    
                    # Emit presentation closed event to all connected clients
                    socketio.emit('presentation_closed', {
                        'timestamp': time.time(),
                        'message': 'Presentation file closed - timing reset'
                    })
            
            elif current_slide is not None and total_slides is not None:
                # Check if slide has changed or if we don't have total slides cached
                if slide_monitor['current_slide'] != current_slide or slide_monitor['total_slides'] != total_slides:
                    old_slide = slide_monitor['current_slide']
                    current_time = time.time()
                    
                    # If we had a previous slide timer running AND presentation is running, record the time spent
                    if (old_slide is not None and slide_monitor['slide_timer_start'] is not None 
                        and slide_monitor['presentation_running']):
                        time_spent = current_time - slide_monitor['slide_timer_start']
                        if old_slide in slide_monitor['slide_timers']:
                            slide_monitor['slide_timers'][old_slide] += time_spent
                        else:
                            slide_monitor['slide_timers'][old_slide] = time_spent
                        
                        # Get timing status for the completed slide
                        timing_status = get_slide_timing_status(old_slide, time_spent)
                        status_emoji = "✅" if timing_status['status'] == 'on_time' else "⚠️" if timing_status['status'] == 'warning' else "🔴"
                        print(f"⏱️  Recorded {time_spent:.1f}s on slide {old_slide} {status_emoji}")
                        
                        # Emit timing update for completed slide
                        socketio.emit('slide_timing_update', {
                            'slideNumber': old_slide,
                            'timingStatus': timing_status,
                            'timestamp': current_time
                        })
                    
                    # Update slide tracking state
                    slide_monitor['current_slide'] = current_slide
                    slide_monitor['total_slides'] = total_slides
                    slide_monitor['last_check'] = current_time
                    
                    # Start new slide timer ONLY if presentation is running
                    if slide_monitor['presentation_running']:
                        slide_monitor['slide_timer_start'] = current_time
                        slide_timer_reset = True
                        print(f"📍 Slide changed: {old_slide} → {current_slide} (of {total_slides}) - Timer reset")
                    else:
                        slide_monitor['slide_timer_start'] = None
                        slide_timer_reset = False
                        print(f"📍 Slide changed: {old_slide} → {current_slide} (of {total_slides}) - No timer (presentation not running)")
                    
                    # Get current slide timing status (for new slide)
                    current_slide_timing = get_slide_timing_status(current_slide, 0)
                    
                    # Calculate presentation timing status if presentation is running
                    presentation_timing_status = None
                    if slide_monitor['presentation_running'] and slide_monitor['presentation_start_time']:
                        # Calculate total elapsed time since presentation started
                        total_elapsed = current_time - slide_monitor['presentation_start_time']
                        presentation_timing_status = get_presentation_timing_status(current_slide, total_elapsed)
                    
                    # Emit slide change event to all connected clients
                    socketio.emit('slide_changed', {
                        'slideNumber': current_slide,
                        'totalSlides': total_slides,
                        'previousSlide': old_slide,
                        'timestamp': current_time,
                        'slideTimerReset': slide_timer_reset,  # Only reset if presentation is running
                        'presentationRunning': slide_monitor['presentation_running'],
                        'timingStatus': current_slide_timing,  # Include timing info for new slide
                        'presentationTimingStatus': presentation_timing_status  # Include overall presentation status
                    })
                
                # Check for timing warnings on current slide (every monitoring cycle)
                elif (slide_monitor['presentation_running'] and slide_monitor['slide_timer_start'] is not None 
                      and current_slide is not None):
                    current_elapsed = time.time() - slide_monitor['slide_timer_start']
                    timing_status = get_slide_timing_status(current_slide, current_elapsed)
                    
                    # Also calculate presentation timing status for periodic updates
                    current_time = time.time()
                    presentation_timing_status = None
                    if slide_monitor['presentation_start_time']:
                        total_elapsed = current_time - slide_monitor['presentation_start_time']
                        presentation_timing_status = get_presentation_timing_status(current_slide, total_elapsed)
                    
                    # Emit periodic timing updates for active slide (only if it has planned timing)
                    if timing_status['hasPlannedTime']:
                        socketio.emit('current_slide_timing', {
                            'slideNumber': current_slide,
                            'timingStatus': timing_status,
                            'presentationTimingStatus': presentation_timing_status,
                            'timestamp': time.time()
                        })
            
            time.sleep(slide_monitor['interval'])
            
        except Exception as e:
            print(f"❌ Error in slide monitor: {e}")
            time.sleep(slide_monitor['interval'])
    
    print("🛑 Slide monitor stopped")

def start_slide_monitoring():
    """Start the background slide monitoring"""
    if not slide_monitor['active']:
        slide_monitor['active'] = True
        slide_monitor['current_slide'] = get_slide_number_internal()
        slide_monitor['total_slides'] = get_total_slides_internal()
        # Don't start slide timer here - wait for presentation to start
        slide_monitor['slide_timer_start'] = None
        
        # Load slide timings from file when monitoring starts
        load_slide_timings()
        
        slide_monitor['thread'] = threading.Thread(target=slide_monitor_worker, daemon=True)
        slide_monitor['thread'].start()
        return True
    return False

def stop_slide_monitoring():
    """Stop the background slide monitoring"""
    if slide_monitor['active']:
        slide_monitor['active'] = False
        if slide_monitor['thread']:
            slide_monitor['thread'].join(timeout=5)
        slide_monitor['thread'] = None
        return True
    return False

# WebSocket event handlers
@socketio.on('connect')
def handle_connect():
    print(f"🔗 Client connected: {request.sid}")
    # Send current slide state to newly connected client
    current_slide = get_slide_number_internal()
    total_slides = get_total_slides_internal()
    
    if current_slide is not None and total_slides is not None:
        # Calculate current elapsed time if timer is running
        current_elapsed = 0
        if (slide_monitor['slide_timer_start'] is not None and 
            slide_monitor['presentation_running']):
            current_elapsed = time.time() - slide_monitor['slide_timer_start']
        
        # Get timing status for current slide
        timing_status = get_slide_timing_status(current_slide, current_elapsed)
        
        emit('slide_changed', {
            'slideNumber': current_slide,
            'totalSlides': total_slides,
            'previousSlide': None,
            'timestamp': time.time(),
            'slideTimerReset': slide_monitor['presentation_running'],  # Only reset if presentation is running
            'presentationRunning': slide_monitor['presentation_running'],
            'timingStatus': timing_status
        })
    else:
        # No presentation open - send closed state
        emit('presentation_closed', {
            'timestamp': time.time(),
            'message': 'No presentation currently open'
        })

@socketio.on('disconnect')
def handle_disconnect():
    print(f"🔌 Client disconnected: {request.sid}")

@socketio.on('start_monitoring')
def handle_start_monitoring():
    """Client requests to start slide monitoring"""
    success = start_slide_monitoring()
    emit('monitoring_status', {'active': slide_monitor['active'], 'started': success})
    print(f"📡 Monitoring {'started' if success else 'already active'}")

@socketio.on('stop_monitoring')
def handle_stop_monitoring():
    """Client requests to stop slide monitoring"""
    success = stop_slide_monitoring()
    emit('monitoring_status', {'active': slide_monitor['active'], 'stopped': success})
    print(f"📡 Monitoring {'stopped' if success else 'already inactive'}")

# REST API endpoints (existing functionality)
@app.route('/next_slide', methods=['GET'])
def next_slide():
    script = """
    tell application "Keynote"
        activate
        if exists front document then
            show next of front document
            return "Moved to next slide."
        else
            return "No Keynote document open."
        end if
    end tell
    """
    response = run_applescript(script)
    return jsonify({"status": "success", "message": response})

@app.route('/previous_slide', methods=['GET'])
def previous_slide():
    script = """
    tell application "Keynote"
        activate
        if exists front document then
            show previous of front document
            return "Moved to previous slide."
        else
            return "No Keynote document open."
        end if
    end tell
    """
    response = run_applescript(script)
    return jsonify({"status": "success", "message": response})

@app.route('/current_slide_number', methods=['GET'])
def current_slide_number():
    slide_number = get_slide_number_internal()
    
    if slide_number is None:
        return jsonify({"status": "error", "message": "Could not retrieve slide number or no document open"})
    
    return jsonify({"status": "success", "slideNumber": slide_number})

@app.route('/total_slides', methods=['GET'])
def total_slides():
    total_slides = get_total_slides_internal()
    
    if total_slides is None:
        return jsonify({"status": "error", "message": "Could not retrieve total slides or no document open"})
    
    return jsonify({"status": "success", "totalSlides": total_slides})

@app.route('/presentation_info', methods=['GET'])
def presentation_info():
    """Get both current slide and total slides in one call"""
    current_slide = get_slide_number_internal()
    total_slides = get_total_slides_internal()
    
    if current_slide is None or total_slides is None:
        return jsonify({"status": "error", "message": "Could not retrieve presentation info or no document open"})
    
    return jsonify({
        "status": "success", 
        "currentSlide": current_slide,
        "totalSlides": total_slides
    })

@app.route('/goto_slide/<int:slide_number>', methods=['GET'])
def goto_slide(slide_number):
    script = f"""
    tell application "Keynote"
        activate
        if exists front document then
            try
                -- Check if we're in slideshow mode
                set isInSlideshow to false
                try
                    set currentSlideInSlideshow to current slide of slideshow of front document
                    set isInSlideshow to true
                on error
                    set isInSlideshow to false
                end try
                
                if isInSlideshow then
                    -- In slideshow mode, use show slide
                    show slide {slide_number} of front document
                    return "Navigated to slide {slide_number} in slideshow mode."
                else
                    -- In normal editing mode, select the slide in the editor
                    set current slide of front document to slide {slide_number} of front document
                    return "Selected slide {slide_number} in editing mode."
                end if
            on error errMsg
                return "ERROR: " & errMsg
            end try
        else
            return "ERROR: No Keynote document open."
        end if
    end tell
    """
    
    # Run AppleScript to navigate to slide
    script_output = run_applescript(script)
    
    # Check for errors
    if script_output.startswith("ERROR:") or "No Keynote document open" in script_output or "Error executing script:" in script_output:
        return jsonify({"status": "error", "message": script_output})
    
    return jsonify({"status": "success", "message": script_output, "targetSlide": slide_number})

def get_total_planned_time():
    """Calculate total planned presentation time by summing all slide timings"""
    if not slide_monitor['planned_timings']:
        return None
    
    return sum(slide_monitor['planned_timings'].values())

@app.route('/start_presentation', methods=['GET'])
def start_presentation():
    script = """
    tell application "Keynote"
        activate
        if exists front document then
            start slideshow of front document
            return "Presentation started."
        else
            return "No Keynote document open."
        end if
    end tell
    """
    response = run_applescript(script)
    
    # Set presentation as running and initialize slide timer
    current_time = time.time()
    slide_monitor['presentation_running'] = True
    slide_monitor['slide_timer_start'] = current_time
    slide_monitor['presentation_start_time'] = current_time  # Track presentation start
    
    # Load slide timings when presentation starts (in case document changed)
    load_slide_timings()
    
    # Automatically start monitoring when presentation starts
    start_slide_monitoring()
    
    # Get current slide timing status
    current_slide = slide_monitor['current_slide']
    current_timing = get_slide_timing_status(current_slide, 0) if current_slide else None
    
    # Calculate total planned time
    total_planned_time = get_total_planned_time()
    
    # Calculate initial presentation timing status
    presentation_timing_status = get_presentation_timing_status(current_slide, 0) if current_slide else None
    
    # Emit presentation started event to all clients
    socketio.emit('presentation_started', {
        'timestamp': current_time,
        'slideTimerReset': True,
        'currentSlide': current_slide,
        'timingStatus': current_timing,
        'totalPlannedSlides': len(slide_monitor['planned_timings']),
        'totalPlannedTime': total_planned_time,  # Add total planned time
        'presentationTimingStatus': presentation_timing_status  # Add presentation timing status
    })
    
    print("🎬 Presentation started - slide timer initialized")
    if slide_monitor['planned_timings']:
        print(f"📋 Loaded timing for {len(slide_monitor['planned_timings'])} slides")
        if total_planned_time:
            print(f"⏱️ Total planned time: {total_planned_time/60:.1f} minutes")
    
    return jsonify({"status": "success", "message": response})

@app.route('/stop_presentation', methods=['GET'])
def stop_presentation():
    script = """
    tell application "Keynote"
        activate
        if exists front document then
            stop slideshow of front document
            return "Presentation stopped."
        else
            return "No Keynote document open."
        end if
    end tell
    """
    response = run_applescript(script)
    
    # Record final slide time if we were timing
    if (slide_monitor['current_slide'] is not None and slide_monitor['slide_timer_start'] is not None 
        and slide_monitor['presentation_running']):
        current_time = time.time()
        time_spent = current_time - slide_monitor['slide_timer_start']
        slide_number = slide_monitor['current_slide']
        if slide_number in slide_monitor['slide_timers']:
            slide_monitor['slide_timers'][slide_number] += time_spent
        else:
            slide_monitor['slide_timers'][slide_number] = time_spent
        print(f"⏱️  Final: Recorded {time_spent:.1f}s on slide {slide_number}")
    
    # Clear presentation state and slide timer
    slide_monitor['presentation_running'] = False
    slide_monitor['slide_timer_start'] = None
    slide_monitor['presentation_start_time'] = None  # Clear presentation start time
    
    # Automatically stop monitoring when presentation stops
    stop_slide_monitoring()
    
    # Emit presentation stopped event to all clients
    socketio.emit('presentation_stopped', {
        'timestamp': time.time()
    })
    
    print("🛑 Presentation stopped - slide timer cleared")
    
    return jsonify({"status": "success", "message": response})

# New endpoints for monitoring control
@app.route('/monitoring/start', methods=['POST'])
def start_monitoring_endpoint():
    """REST endpoint to start slide monitoring"""
    success = start_slide_monitoring()
    return jsonify({
        "status": "success" if success else "info",
        "message": "Monitoring started" if success else "Monitoring already active",
        "active": slide_monitor['active']
    })

@app.route('/monitoring/stop', methods=['POST'])
def stop_monitoring_endpoint():
    """REST endpoint to stop slide monitoring"""
    success = stop_slide_monitoring()
    return jsonify({
        "status": "success" if success else "info",
        "message": "Monitoring stopped" if success else "Monitoring already inactive", 
        "active": slide_monitor['active']
    })

@app.route('/monitoring/status', methods=['GET'])
def monitoring_status():
    """Get current monitoring status"""
    return jsonify({
        "status": "success",
        "active": slide_monitor['active'],
        "currentSlide": slide_monitor['current_slide'],
        "totalSlides": slide_monitor['total_slides'],
        "lastCheck": slide_monitor['last_check'],
        "interval": slide_monitor['interval']
    })

@app.route('/slide_timer_stats', methods=['GET'])
def slide_timer_stats():
    """Get slide timer statistics"""
    try:
        current_slide = slide_monitor['current_slide']
        current_elapsed = 0
        
        # Calculate current slide elapsed time if timer is running AND presentation is running
        if (slide_monitor['slide_timer_start'] is not None and current_slide is not None 
            and slide_monitor['presentation_running']):
            current_elapsed = time.time() - slide_monitor['slide_timer_start']
        
        # Get current slide timing status
        current_timing = get_slide_timing_status(current_slide, current_elapsed) if current_slide else None
        
        # Calculate total planned time
        total_planned_time = get_total_planned_time()
        
        return jsonify({
            "status": "success",
            "currentSlide": current_slide,
            "currentSlideElapsed": current_elapsed,
            "currentTiming": current_timing,
            "slideTimers": slide_monitor['slide_timers'],
            "plannedTimings": slide_monitor['planned_timings'],
            "totalPlannedTime": total_planned_time,  # Add total planned time
            "monitoringActive": slide_monitor['active'],
            "presentationRunning": slide_monitor['presentation_running'],
            "timingFilePath": slide_monitor['timing_file_path']
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/slide_timings/load', methods=['POST'])
def load_timings_endpoint():
    """Manually reload slide timings from file"""
    success = load_slide_timings()
    total_planned_time = get_total_planned_time()
    
    return jsonify({
        "status": "success" if success else "warning",
        "message": f"Loaded timing for {len(slide_monitor['planned_timings'])} slides" if success else "No timing file found or error loading",
        "plannedTimings": slide_monitor['planned_timings'],
        "totalPlannedTime": total_planned_time,  # Add total planned time
        "timingFilePath": slide_monitor['timing_file_path'],
        "keynoteDocumentPath": slide_monitor['keynote_document_path']
    })

@app.route('/slide_timings/create_default', methods=['POST'])
def create_default_timing_file():
    """Create a default JSON timing file with 1 minute per slide"""
    try:
        # Get current Keynote document path
        keynote_path = get_keynote_document_path()
        if not keynote_path:
            return jsonify({
                "status": "error",
                "message": "No Keynote document open"
            })
        
        # Get total slides
        total_slides = get_total_slides_internal()
        if total_slides is None or total_slides <= 0:
            return jsonify({
                "status": "error",
                "message": "Could not determine total slides"
            })
        
        # Generate timing file path (JSON format)
        base_path = os.path.splitext(keynote_path)[0]
        timing_file_path = base_path + '.json'
        presentation_name = os.path.basename(base_path)
        
        # Check if file already exists
        if os.path.exists(timing_file_path):
            return jsonify({
                "status": "warning",
                "message": "JSON timing file already exists",
                "timingFilePath": timing_file_path,
                "overwrite": False
            })
        
        # Create default JSON timing file
        json_data = create_timing_json_structure(presentation_name, total_slides, 60)
        
        with open(timing_file_path, 'w') as f:
            json.dump(json_data, f, indent=2)
        
        # Load the newly created timing file
        load_slide_timings()
        total_planned_time = get_total_planned_time()
        
        return jsonify({
            "status": "success",
            "message": f"Created default JSON timing file with {total_slides} slides at 1 minute each",
            "timingFilePath": timing_file_path,
            "totalSlides": total_slides,
            "plannedTimings": slide_monitor['planned_timings'],
            "totalPlannedTime": total_planned_time,
            "metadata": slide_monitor.get('timing_metadata', {}),
            "presentationInfo": slide_monitor.get('presentation_info', {}),
            "created": True,
            "format": "json"
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })

@app.route('/debug/timing_creation', methods=['GET'])
def debug_timing_creation():
    """Debug endpoint to check timing file creation status"""
    try:
        # Get current Keynote document path
        keynote_path = get_keynote_document_path()
        
        debug_info = {
            "keynoteDocumentPath": keynote_path,
            "keynoteDocumentOpen": keynote_path is not None,
        }
        
        if keynote_path:
            # Get total slides
            total_slides = get_total_slides_internal()
            debug_info["totalSlides"] = total_slides
            debug_info["totalSlidesValid"] = total_slides is not None and total_slides > 0
            
            # Generate timing file paths
            base_path = os.path.splitext(keynote_path)[0]
            json_timing_file_path = base_path + '.json'
            txt_timing_file_path = base_path + '.txt'
            
            debug_info["expectedJsonTimingFilePath"] = json_timing_file_path
            debug_info["expectedTxtTimingFilePath"] = txt_timing_file_path
            debug_info["jsonTimingFileExists"] = os.path.exists(json_timing_file_path)
            debug_info["txtTimingFileExists"] = os.path.exists(txt_timing_file_path)
            debug_info["needsMigration"] = os.path.exists(txt_timing_file_path) and not os.path.exists(json_timing_file_path)
            
            # Check current slide monitor state
            debug_info["slideMonitorState"] = {
                "keynoteDocumentPath": slide_monitor.get('keynote_document_path'),
                "timingFilePath": slide_monitor.get('timing_file_path'),
                "plannedTimingsCount": len(slide_monitor.get('planned_timings', {})),
                "currentSlide": slide_monitor.get('current_slide'),
                "totalSlides": slide_monitor.get('total_slides')
            }
        
        return jsonify({
            "status": "success",
            "debugInfo": debug_info
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "debugInfo": {}
        })

@app.route('/powerpoint/convert_to_keynote', methods=['POST'])
def convert_powerpoint_to_keynote():
    """Manually convert current PowerPoint document to Keynote"""
    try:
        keynote_path = auto_convert_powerpoint_to_keynote()
        
        if keynote_path:
            # Load timings for the new Keynote file
            timings_loaded = load_slide_timings()
            
            return jsonify({
                "status": "success",
                "message": f"Successfully converted to Keynote file",
                "keynoteFilePath": keynote_path,
                "keynoteFileName": os.path.basename(keynote_path),
                "timingsLoaded": len(slide_monitor['planned_timings']) > 0,
                "timingFilePath": slide_monitor.get('timing_file_path'),
                "totalSlides": get_total_slides_internal()
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Could not convert PowerPoint to Keynote. Make sure a presentation is open in Keynote."
            })
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })

@app.route('/slide_timings/status', methods=['GET'])
def timing_status_endpoint():
    """Get current timing status for all slides"""
    try:
        current_slide = slide_monitor['current_slide']
        current_elapsed = 0
        
        # Calculate current slide elapsed time if timer is running
        if (slide_monitor['slide_timer_start'] is not None and current_slide is not None 
            and slide_monitor['presentation_running']):
            current_elapsed = time.time() - slide_monitor['slide_timer_start']
        
        # Get timing status for current slide
        current_timing = get_slide_timing_status(current_slide, current_elapsed) if current_slide else None
        
        # Get timing status for all completed slides
        completed_timings = {}
        for slide_num, actual_time in slide_monitor['slide_timers'].items():
            completed_timings[slide_num] = get_slide_timing_status(slide_num, actual_time)
        
        return jsonify({
            "status": "success",
            "currentSlide": current_slide,
            "currentTiming": current_timing,
            "completedTimings": completed_timings,
            "plannedTimings": slide_monitor['planned_timings'],
            "presentationRunning": slide_monitor['presentation_running'],
            "timingFilePath": slide_monitor['timing_file_path']
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/slide_timings/slide/<int:slide_number>', methods=['GET'])
def individual_slide_timing(slide_number):
    """Get timing information for a specific slide"""
    try:
        # Get actual time spent on this slide
        actual_time = slide_monitor['slide_timers'].get(slide_number, 0)
        
        # If this is the current slide and presentation is running, add elapsed time
        if (slide_number == slide_monitor['current_slide'] and 
            slide_monitor['slide_timer_start'] is not None and 
            slide_monitor['presentation_running']):
            actual_time += time.time() - slide_monitor['slide_timer_start']
        
        timing_status = get_slide_timing_status(slide_number, actual_time)
        
        return jsonify({
            "status": "success",
            "slideNumber": slide_number,
            "timingStatus": timing_status,
            "isCurrentSlide": slide_number == slide_monitor['current_slide']
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/presentation/total_planned_time', methods=['GET'])
def get_total_planned_time_endpoint():
    """Get the total planned presentation time"""
    try:
        total_planned_time = get_total_planned_time()
        
        return jsonify({
            "status": "success",
            "totalPlannedTime": total_planned_time,
            "totalPlannedSlides": len(slide_monitor['planned_timings']),
            "plannedTimings": slide_monitor['planned_timings'],
            "timingFilePath": slide_monitor['timing_file_path'],
            "metadata": slide_monitor.get('timing_metadata', {}),
            "presentationInfo": slide_monitor.get('presentation_info', {})
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/slide_timings/metadata', methods=['GET'])
def get_timing_metadata():
    """Get comprehensive timing file metadata and structure information"""
    try:
        timing_metadata = slide_monitor.get('timing_metadata', {})
        presentation_info = slide_monitor.get('presentation_info', {})
        
        # Calculate current statistics
        planned_timings = slide_monitor.get('planned_timings', {})
        total_slides_with_timing = len(planned_timings)
        total_planned_time = sum(planned_timings.values()) if planned_timings else 0
        
        # Count custom timings (non-60 second)
        custom_timing_count = sum(1 for time in planned_timings.values() if time != 60)
        
        # Calculate average time per slide
        avg_time_per_slide = total_planned_time / total_slides_with_timing if total_slides_with_timing > 0 else 0
        
        return jsonify({
            "status": "success",
            "timingFilePath": slide_monitor.get('timing_file_path'),
            "presentationInfo": presentation_info,
            "metadata": timing_metadata,
            "currentStatistics": {
                "totalSlidesWithTiming": total_slides_with_timing,
                "totalPlannedTime": total_planned_time,
                "estimatedDuration": f"{total_planned_time // 60:.0f}m {total_planned_time % 60:.0f}s",
                "slidesWithCustomTiming": custom_timing_count,
                "averageTimePerSlide": avg_time_per_slide,
                "shortestSlide": min(planned_timings.values()) if planned_timings else 0,
                "longestSlide": max(planned_timings.values()) if planned_timings else 0
            },
            "format": {
                "version": "1.0",
                "type": "json",
                "supportedFeatures": ["notes", "descriptions", "importance", "metadata"]
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

def get_remaining_planned_time(current_slide_num):
    """Calculate remaining planned time for slides after the current slide"""
    if not slide_monitor['planned_timings'] or current_slide_num is None:
        return None
    
    remaining_time = 0
    for slide_num, planned_time in slide_monitor['planned_timings'].items():
        if slide_num > current_slide_num:
            remaining_time += planned_time
    
    return remaining_time

def get_presentation_timing_status(current_slide_num, elapsed_time):
    """Calculate comprehensive timing status for the entire presentation"""
    if not slide_monitor['planned_timings'] or current_slide_num is None:
        return None
    
    # Calculate expected time to reach the START of current slide
    expected_time_to_current_slide = 0
    for slide_num, planned_time in slide_monitor['planned_timings'].items():
        if slide_num < current_slide_num:
            expected_time_to_current_slide += planned_time
    
    # Calculate how far behind/ahead we are compared to schedule
    # Negative = behind schedule, Positive = ahead of schedule
    variance = expected_time_to_current_slide - elapsed_time
    
    # Determine status based on simplified 3-state system
    if variance >= -60:  # Less than 60 seconds behind, or ahead
        status = 'on_time'  # Green
    elif variance >= -120:  # 60 seconds to 2 minutes behind
        status = 'losing_progress'  # Orange
    else:  # More than 2 minutes behind
        status = 'off_track'  # Red
    
    # Calculate remaining planned time and projected total
    total_planned_time = get_total_planned_time()
    remaining_planned_time = get_remaining_planned_time(current_slide_num)
    projected_total_time = elapsed_time + remaining_planned_time if remaining_planned_time else None
    
    return {
        'totalPlannedTime': total_planned_time,
        'remainingPlannedTime': remaining_planned_time,
        'projectedTotalTime': projected_total_time,
        'expectedTimeToCurrentSlide': expected_time_to_current_slide,
        'variance': variance,  # Positive = ahead, Negative = behind
        'status': status,
        'currentSlide': current_slide_num,
        'elapsedTime': elapsed_time
    }

@app.route('/presentation/timing_status', methods=['GET'])
def get_presentation_timing_status_endpoint():
    """Get current presentation timing status"""
    try:
        if not slide_monitor['presentation_running'] or not slide_monitor['presentation_start_time']:
            return jsonify({
                "status": "info",
                "message": "Presentation not running",
                "presentationRunning": False
            })
        
        current_slide = slide_monitor['current_slide']
        if current_slide is None:
            return jsonify({
                "status": "error",
                "message": "Could not determine current slide"
            })
        
        # Calculate total elapsed time
        current_time = time.time()
        total_elapsed = current_time - slide_monitor['presentation_start_time']
        
        # Get presentation timing status
        presentation_timing_status = get_presentation_timing_status(current_slide, total_elapsed)
        
        return jsonify({
            "status": "success",
            "presentationTimingStatus": presentation_timing_status,
            "currentSlide": current_slide,
            "totalElapsed": total_elapsed,
            "presentationRunning": slide_monitor['presentation_running']
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# File Browser and Opening functionality
@app.route('/files/browse', methods=['GET'])
def browse_files():
    """Browse files and directories on the server"""
    try:
        path = request.args.get('path', os.path.expanduser('~'))  # Default to home directory
        
        # Security check - ensure path is within user's home directory or common presentation locations
        allowed_paths = [
            os.path.expanduser('~'),
            '/Users',
            '/Applications'
        ]
        
        # Normalize the path
        abs_path = os.path.abspath(path)
        
        # Check if path is allowed (must start with one of the allowed paths)
        if not any(abs_path.startswith(allowed) for allowed in allowed_paths):
            return jsonify({
                "status": "error",
                "message": "Access to this directory is not allowed"
            })
        
        if not os.path.exists(abs_path):
            return jsonify({
                "status": "error",
                "message": "Path does not exist"
            })
        
        if not os.path.isdir(abs_path):
            return jsonify({
                "status": "error",
                "message": "Path is not a directory"
            })
        
        # Get directory contents
        items = []
        try:
            for item in sorted(os.listdir(abs_path)):
                if item.startswith('.'):  # Skip hidden files
                    continue
                
                item_path = os.path.join(abs_path, item)
                
                try:
                    stat_info = os.stat(item_path)
                    is_dir = os.path.isdir(item_path)
                    
                    # For files, check if it's a Keynote or PowerPoint file
                    is_keynote = False
                    is_powerpoint = False
                    if not is_dir:
                        _, ext = os.path.splitext(item.lower())
                        is_keynote = ext == '.key'
                        is_powerpoint = ext in ['.ppt', '.pptx']
                    
                    items.append({
                        'name': item,
                        'path': item_path,
                        'isDirectory': is_dir,
                        'isKeynoteFile': is_keynote,
                        'isPowerPointFile': is_powerpoint,
                        'isPresentationFile': is_keynote or is_powerpoint,
                        'size': stat_info.st_size if not is_dir else None,
                        'modified': stat_info.st_mtime
                    })
                except (OSError, PermissionError):
                    # Skip items we can't access
                    continue
                    
        except PermissionError:
            return jsonify({
                "status": "error",
                "message": "Permission denied accessing directory"
            })
        
        # Get parent directory path
        parent_path = os.path.dirname(abs_path) if abs_path != '/' else None
        
        return jsonify({
            "status": "success",
            "currentPath": abs_path,
            "parentPath": parent_path,
            "items": items
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })

@app.route('/files/open_keynote', methods=['POST'])
def open_keynote_file():
    """Open a specific presentation file (Keynote or PowerPoint) with Keynote"""
    try:
        data = request.get_json()
        if not data or 'filePath' not in data:
            return jsonify({
                "status": "error",
                "message": "File path is required"
            })
        
        file_path = data['filePath']
        
        # Security check - ensure file exists and is a .key file
        if not os.path.exists(file_path):
            return jsonify({
                "status": "error",
                "message": "File does not exist"
            })
        
        # Check if it's a supported presentation file
        file_ext = os.path.splitext(file_path.lower())[1]
        if file_ext not in ['.key', '.ppt', '.pptx']:
            return jsonify({
                "status": "error",
                "message": "File is not a supported presentation format (.key, .ppt, .pptx)"
            })
        
        # Use AppleScript to open the presentation file in Keynote
        file_name = os.path.basename(file_path)
        script = f'''
        tell application "Keynote"
            activate
            try
                open POSIX file "{file_path}"
                return "Successfully opened: {file_name}"
            on error errMsg
                return "ERROR: " & errMsg
            end try
        end tell
        '''
        
        script_output = run_applescript(script)
        
        # Check for errors
        if script_output.startswith("ERROR:"):
            return jsonify({
                "status": "error",
                "message": script_output
            })
        
        # Wait a moment for the file to open, then get presentation info
        time.sleep(1)
        current_slide = get_slide_number_internal()
        total_slides = get_total_slides_internal()
        
        # Auto-convert PowerPoint to Keynote if needed (pass original path for PowerPoint files)
        original_powerpoint_path = file_path if file_ext in ['.ppt', '.pptx'] else None
        keynote_path = auto_convert_powerpoint_to_keynote(original_powerpoint_path)
        timing_file_path = os.path.splitext(keynote_path)[0] + '.txt' if keynote_path else None
        timing_file_existed = os.path.exists(timing_file_path) if timing_file_path else False
        
        # Reload slide timings for the newly opened presentation
        timings_loaded = load_slide_timings(original_powerpoint_path)
        timing_file_created = not timing_file_existed and os.path.exists(slide_monitor.get('timing_file_path', ''))
        
        # Get the final Keynote file path for response
        final_keynote_path = keynote_path or file_path
        
        # Check if PowerPoint was converted to Keynote
        was_converted = (keynote_path and keynote_path != file_path)
        
        return jsonify({
            "status": "success",
            "message": script_output,
            "originalFilePath": file_path,
            "originalFileName": file_name,
            "originalFileType": file_ext,
            "keynoteFilePath": final_keynote_path,
            "wasConverted": was_converted,
            "conversionMessage": f"Auto-saved PowerPoint as Keynote: {os.path.basename(keynote_path)}" if was_converted else None,
            "currentSlide": current_slide,
            "totalSlides": total_slides,
            "timingsLoaded": len(slide_monitor['planned_timings']) > 0,
            "timingFilePath": slide_monitor['timing_file_path'],
            "timingFileCreated": timing_file_created,
            "timingFileExisted": timing_file_existed
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })

@app.route('/files/recent_keynote_files', methods=['GET'])
def get_recent_keynote_files():
    """Get a list of recently accessed presentation files (Keynote and PowerPoint)"""
    try:
        keynote_files = []
        
        # Common locations to look for Keynote files
        search_paths = [
            os.path.expanduser('~/Documents'),
            os.path.expanduser('~/Desktop'),
            os.path.expanduser('~/Downloads')
        ]
        
        for search_path in search_paths:
            if os.path.exists(search_path):
                try:
                    for root, dirs, files in os.walk(search_path):
                        # Limit depth to avoid searching too deep
                        depth = root[len(search_path):].count(os.sep)
                        if depth >= 3:  # Max 3 levels deep
                            dirs[:] = []  # Don't go deeper
                            continue
                            
                        for file in files:
                            file_lower = file.lower()
                            if file_lower.endswith('.key') or file_lower.endswith('.ppt') or file_lower.endswith('.pptx'):
                                file_path = os.path.join(root, file)
                                try:
                                    stat_info = os.stat(file_path)
                                    _, ext = os.path.splitext(file_lower)
                                    keynote_files.append({
                                        'name': file,
                                        'path': file_path,
                                        'directory': root,
                                        'size': stat_info.st_size,
                                        'modified': stat_info.st_mtime,
                                        'fileType': ext,
                                        'isKeynoteFile': ext == '.key',
                                        'isPowerPointFile': ext in ['.ppt', '.pptx'],
                                        'isPresentationFile': True
                                    })
                                except (OSError, PermissionError):
                                    continue
                except (OSError, PermissionError):
                    continue
        
        # Sort by modification time (most recent first)
        keynote_files.sort(key=lambda x: x['modified'], reverse=True)
        
        # Limit to top 20 most recent
        keynote_files = keynote_files[:20]
        
        return jsonify({
            "status": "success",
            "files": keynote_files,
            "count": len(keynote_files),
            "message": f"Found {len(keynote_files)} presentation files (.key, .ppt, .pptx)"
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })

@app.route('/slide_timings/update/<int:slide_number>', methods=['PUT', 'POST'])
def update_slide_timing(slide_number):
    """Update the planned timing for a specific slide"""
    try:
        data = request.get_json()
        if not data or 'plannedTime' not in data:
            return jsonify({
                "status": "error",
                "message": "plannedTime value is required"
            })
        
        new_planned_time = data['plannedTime']
        
        # Validate the new timing value
        try:
            new_planned_time = float(new_planned_time)
            if new_planned_time < 0:
                return jsonify({
                    "status": "error",
                    "message": "Planned time must be a positive number"
                })
        except (ValueError, TypeError):
            return jsonify({
                "status": "error",
                "message": "Planned time must be a valid number"
            })
        
        # Check if we have a timing file loaded
        if not slide_monitor['timing_file_path'] or not os.path.exists(slide_monitor['timing_file_path']):
            return jsonify({
                "status": "error",
                "message": "No timing file loaded. Please load or create a timing file first."
            })
        
        # Load current JSON data
        try:
            with open(slide_monitor['timing_file_path'], 'r') as f:
                timing_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            return jsonify({
                "status": "error",
                "message": f"Error reading timing file: {e}"
            })
        
        # Validate JSON structure
        if not isinstance(timing_data, dict) or 'slideTimings' not in timing_data:
            return jsonify({
                "status": "error",
                "message": "Invalid timing file format"
            })
        
        slide_str = str(slide_number)
        
        # Ensure slide entry exists
        if slide_str not in timing_data['slideTimings']:
            # Create new slide entry with default values
            timing_data['slideTimings'][slide_str] = {
                "plannedTime": new_planned_time,
                "notes": "",
                "description": f"Slide {slide_number}",
                "importance": "normal"
            }
        else:
            # Update existing slide timing
            timing_data['slideTimings'][slide_str]['plannedTime'] = new_planned_time
        
        # Get current values for comparison
        old_planned_time = slide_monitor['planned_timings'].get(slide_number, 60)  # Default 60 if not found
        
        # Update in-memory data structure
        slide_monitor['planned_timings'][slide_number] = new_planned_time
        
        # Recalculate metadata
        total_slides = len(timing_data['slideTimings'])
        total_planned_time = sum(slide_data['plannedTime'] for slide_data in timing_data['slideTimings'].values())
        slides_with_custom_timing = sum(1 for slide_data in timing_data['slideTimings'].values() 
                                       if slide_data['plannedTime'] != 60)
        average_time_per_slide = total_planned_time / total_slides if total_slides > 0 else 0
        
        # Update metadata in JSON
        if 'metadata' not in timing_data:
            timing_data['metadata'] = {}
        
        timing_data['metadata'].update({
            "totalPlannedTime": total_planned_time,
            "estimatedDuration": f"{total_planned_time // 60:.0f}m {total_planned_time % 60:.0f}s",
            "slidesWithCustomTiming": slides_with_custom_timing,
            "averageTimePerSlide": average_time_per_slide,
            "lastModified": time.time()
        })
        
        # Update presentation info timestamp
        if 'presentationInfo' in timing_data:
            timing_data['presentationInfo']['lastModified'] = time.time()
        
        # Save updated JSON file
        try:
            with open(slide_monitor['timing_file_path'], 'w') as f:
                json.dump(timing_data, f, indent=2)
        except IOError as e:
            return jsonify({
                "status": "error",
                "message": f"Error saving timing file: {e}"
            })
        
        # Update slide_monitor metadata
        slide_monitor['timing_metadata'] = timing_data.get('metadata', {})
        slide_monitor['presentation_info'] = timing_data.get('presentationInfo', {})
        
        # Calculate current slide timing status if this is the current slide
        current_slide_timing_status = None
        current_slide = slide_monitor['current_slide']
        if current_slide == slide_number:
            current_elapsed = 0
            if (slide_monitor['slide_timer_start'] is not None and 
                slide_monitor['presentation_running']):
                current_elapsed = time.time() - slide_monitor['slide_timer_start']
            current_slide_timing_status = get_slide_timing_status(slide_number, current_elapsed)
        
        # Calculate updated presentation timing status if presentation is running
        presentation_timing_status = None
        if slide_monitor['presentation_running'] and slide_monitor['presentation_start_time']:
            current_time = time.time()
            total_elapsed = current_time - slide_monitor['presentation_start_time']
            presentation_timing_status = get_presentation_timing_status(current_slide, total_elapsed)
        
        # Prepare response data
        response_data = {
            "status": "success",
            "message": f"Updated slide {slide_number} timing from {old_planned_time}s to {new_planned_time}s",
            "slideNumber": slide_number,
            "oldPlannedTime": old_planned_time,
            "newPlannedTime": new_planned_time,
            "timingChange": new_planned_time - old_planned_time,
            "updatedMetadata": timing_data['metadata'],
            "totalPlannedTime": total_planned_time,
            "totalPlannedSlides": total_slides,
            "timingFilePath": slide_monitor['timing_file_path'],
            "currentSlideTimingStatus": current_slide_timing_status,
            "presentationTimingStatus": presentation_timing_status,
            "isCurrentSlide": current_slide == slide_number
        }
        
        # Emit real-time update to all connected clients
        socketio.emit('slide_timing_updated', {
            'slideNumber': slide_number,
            'oldPlannedTime': old_planned_time,
            'newPlannedTime': new_planned_time,
            'timingChange': new_planned_time - old_planned_time,
            'totalPlannedTime': total_planned_time,
            'updatedMetadata': timing_data['metadata'],
            'currentSlideTimingStatus': current_slide_timing_status,
            'presentationTimingStatus': presentation_timing_status,
            'isCurrentSlide': current_slide == slide_number,
            'timestamp': time.time()
        })
        
        print(f"📝 Updated slide {slide_number} timing: {old_planned_time}s → {new_planned_time}s")
        print(f"📊 New total planned time: {total_planned_time/60:.1f} minutes")
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })

@app.route('/slide_timings/batch_update', methods=['PUT', 'POST'])
def batch_update_slide_timings():
    """Update multiple slide timings at once"""
    try:
        data = request.get_json()
        if not data or 'slideTimings' not in data:
            return jsonify({
                "status": "error",
                "message": "slideTimings object is required"
            })
        
        slide_timings_updates = data['slideTimings']
        
        # Validate input format
        if not isinstance(slide_timings_updates, dict):
            return jsonify({
                "status": "error",
                "message": "slideTimings must be an object/dictionary"
            })
        
        # Check if we have a timing file loaded
        if not slide_monitor['timing_file_path'] or not os.path.exists(slide_monitor['timing_file_path']):
            return jsonify({
                "status": "error",
                "message": "No timing file loaded. Please load or create a timing file first."
            })
        
        # Load current JSON data
        try:
            with open(slide_monitor['timing_file_path'], 'r') as f:
                timing_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            return jsonify({
                "status": "error",
                "message": f"Error reading timing file: {e}"
            })
        
        # Validate JSON structure
        if not isinstance(timing_data, dict) or 'slideTimings' not in timing_data:
            return jsonify({
                "status": "error",
                "message": "Invalid timing file format"
            })
        
        # Track changes
        updates_made = []
        errors = []
        
        # Process each slide timing update
        for slide_number_str, new_planned_time in slide_timings_updates.items():
            try:
                slide_number = int(slide_number_str)
                new_planned_time = float(new_planned_time)
                
                if new_planned_time < 0:
                    errors.append(f"Slide {slide_number}: Planned time must be positive")
                    continue
                
                # Get old value
                old_planned_time = slide_monitor['planned_timings'].get(slide_number, 60)
                
                # Update in JSON data
                slide_str = str(slide_number)
                if slide_str not in timing_data['slideTimings']:
                    timing_data['slideTimings'][slide_str] = {
                        "plannedTime": new_planned_time,
                        "notes": "",
                        "description": f"Slide {slide_number}",
                        "importance": "normal"
                    }
                else:
                    timing_data['slideTimings'][slide_str]['plannedTime'] = new_planned_time
                
                # Update in-memory data
                slide_monitor['planned_timings'][slide_number] = new_planned_time
                
                updates_made.append({
                    'slideNumber': slide_number,
                    'oldPlannedTime': old_planned_time,
                    'newPlannedTime': new_planned_time,
                    'timingChange': new_planned_time - old_planned_time
                })
                
            except (ValueError, TypeError) as e:
                errors.append(f"Slide {slide_number_str}: Invalid timing value - {e}")
        
        if not updates_made:
            return jsonify({
                "status": "error",
                "message": "No valid updates were processed",
                "errors": errors
            })
        
        # Recalculate metadata
        total_slides = len(timing_data['slideTimings'])
        total_planned_time = sum(slide_data['plannedTime'] for slide_data in timing_data['slideTimings'].values())
        slides_with_custom_timing = sum(1 for slide_data in timing_data['slideTimings'].values() 
                                       if slide_data['plannedTime'] != 60)
        average_time_per_slide = total_planned_time / total_slides if total_slides > 0 else 0
        
        # Update metadata
        if 'metadata' not in timing_data:
            timing_data['metadata'] = {}
        
        timing_data['metadata'].update({
            "totalPlannedTime": total_planned_time,
            "estimatedDuration": f"{total_planned_time // 60:.0f}m {total_planned_time % 60:.0f}s",
            "slidesWithCustomTiming": slides_with_custom_timing,
            "averageTimePerSlide": average_time_per_slide,
            "lastModified": time.time()
        })
        
        # Update presentation info timestamp
        if 'presentationInfo' in timing_data:
            timing_data['presentationInfo']['lastModified'] = time.time()
        
        # Save updated JSON file
        try:
            with open(slide_monitor['timing_file_path'], 'w') as f:
                json.dump(timing_data, f, indent=2)
        except IOError as e:
            return jsonify({
                "status": "error",
                "message": f"Error saving timing file: {e}"
            })
        
        # Update slide_monitor metadata
        slide_monitor['timing_metadata'] = timing_data.get('metadata', {})
        slide_monitor['presentation_info'] = timing_data.get('presentationInfo', {})
        
        # Calculate presentation timing status if presentation is running
        presentation_timing_status = None
        if slide_monitor['presentation_running'] and slide_monitor['presentation_start_time']:
            current_time = time.time()
            total_elapsed = current_time - slide_monitor['presentation_start_time']
            current_slide = slide_monitor['current_slide']
            presentation_timing_status = get_presentation_timing_status(current_slide, total_elapsed)
        
        # Emit real-time update to all connected clients
        socketio.emit('slide_timings_batch_updated', {
            'updates': updates_made,
            'totalPlannedTime': total_planned_time,
            'updatedMetadata': timing_data['metadata'],
            'presentationTimingStatus': presentation_timing_status,
            'timestamp': time.time()
        })
        
        print(f"📝 Batch updated {len(updates_made)} slide timings")
        print(f"📊 New total planned time: {total_planned_time/60:.1f} minutes")
        
        return jsonify({
            "status": "success",
            "message": f"Successfully updated {len(updates_made)} slide timings",
            "updatesApplied": len(updates_made),
            "updates": updates_made,
            "errors": errors,
            "totalPlannedTime": total_planned_time,
            "updatedMetadata": timing_data['metadata'],
            "presentationTimingStatus": presentation_timing_status,
            "timingFilePath": slide_monitor['timing_file_path']
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })

if __name__ == '__main__':
    # To make it accessible from your iPhone, you need to use your Mac's local IP address
    # Replace '0.0.0.0' with your Mac's actual IP address if you have firewall issues or
    # want to be more specific, but '0.0.0.0' allows connections from any interface.
    print("🚀 Starting Keynote Remote Server with real-time slide tracking...")
    socketio.run(app, host='0.0.0.0', port=5050, debug=True)