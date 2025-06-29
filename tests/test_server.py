import subprocess
from server import get_keynote_status
import os
from unittest.mock import MagicMock, mock_open
import json

def test_get_keynote_status_closed(mocker):
    """
    Test get_keynote_status when Keynote is not running or no document is open.
    The script should return 'closed'.
    """
    # Mock subprocess.run to simulate Keynote being closed
    mock_run = mocker.patch('subprocess.run')
    mock_run.return_value.stdout = 'closed'
    mock_run.return_value.stderr = ''
    mock_run.return_value.returncode = 0

    status = get_keynote_status()

    assert status == {"document_open": False, "is_playing": False, "slide_number": None, "document_name": None}
    mock_run.assert_called_once()

def test_get_keynote_status_open_and_playing(mocker):
    """
    Test get_keynote_status when a presentation is open and playing.
    """
    # Mock subprocess.run to simulate Keynote being open and playing
    mock_run = mocker.patch('subprocess.run')
    mock_run.return_value.stdout = "My Presentation.key||5||true"
    mock_run.return_value.stderr = ''
    mock_run.return_value.returncode = 0

    status = get_keynote_status()

    assert status == {"document_open": True, "is_playing": True, "slide_number": 5, "document_name": "My Presentation.key"}
    mock_run.assert_called_once()
    
def test_get_keynote_status_open_and_not_playing(mocker):
    """
    Test get_keynote_status when a presentation is open and not playing.
    """
    mock_run = mocker.patch('subprocess.run')
    mock_run.return_value.stdout = "Another Deck.key||1||false"
    mock_run.return_value.stderr = ''
    mock_run.return_value.returncode = 0

    status = get_keynote_status()

    assert status == {"document_open": True, "is_playing": False, "slide_number": 1, "document_name": "Another Deck.key"}
    mock_run.assert_called_once()

def test_get_keynote_status_script_error(mocker):
    """
    Test get_keynote_status when the AppleScript fails.
    """
    # Mock subprocess.run to simulate an error
    mock_run = mocker.patch('subprocess.run')
    mock_run.side_effect = subprocess.CalledProcessError(1, 'osascript')

    status = get_keynote_status()

    assert status == {"document_open": False, "is_playing": False, "slide_number": None, "document_name": None}
    mock_run.assert_called_once()

def test_get_keynote_status_malformed_output(mocker):
    """
    Test get_keynote_status when the AppleScript returns unexpected output.
    """
    # Mock subprocess.run to return malformed output
    mock_run = mocker.patch('subprocess.run')
    mock_run.return_value.stdout = "just_a_name"
    mock_run.return_value.stderr = ''
    mock_run.return_value.returncode = 0

    status = get_keynote_status()

    assert status == {"document_open": False, "is_playing": False, "slide_number": None, "document_name": None}
    mock_run.assert_called_once()

def test_list_presentations_success(mocker, client):
    """
    Test the /api/list_presentations endpoint for a successful directory listing.
    """
    # Mock os.path.expanduser to control the root directory
    mocker.patch('os.path.expanduser', return_value='/fake/home')

    # Mock os.path.abspath to control path resolution
    mocker.patch('os.path.abspath', side_effect=lambda x: x if x.startswith('/') else os.path.join('/fake/home', x))

    # Mock os.scandir to return a controlled list of directory entries
    mock_entry_dir = MagicMock()
    mock_entry_dir.name = 'presentations'
    mock_entry_dir.is_dir.return_value = True
    mock_entry_dir.is_file.return_value = False
    mock_entry_dir.path = '/fake/home/presentations'

    mock_entry_file = MagicMock()
    mock_entry_file.name = 'test.key'
    mock_entry_file.is_dir.return_value = False
    mock_entry_file.is_file.return_value = True
    mock_entry_file.path = '/fake/home/test.key'

    mock_entry_hidden = MagicMock()
    mock_entry_hidden.name = '.hidden_file'

    # Mock os.scandir to return a context manager that yields an iterator
    mock_scandir_context = MagicMock()
    mock_scandir_context.__enter__.return_value = iter([mock_entry_dir, mock_entry_file, mock_entry_hidden])
    mocker.patch('os.scandir', return_value=mock_scandir_context)

    response = client.get('/api/list_presentations?path=.')

    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert data['path'] == ''
    assert len(data['items']) == 2  # Hidden file should be excluded
    assert data['items'][0]['name'] == 'presentations'
    assert data['items'][0]['type'] == 'directory'
    assert data['items'][1]['name'] == 'test.key'
    assert data['items'][1]['type'] == 'file'


def test_list_presentations_path_traversal(client, mocker):
    """
    Test that the /api/list_presentations endpoint prevents path traversal.
    """
    mocker.patch('os.path.expanduser', return_value='/fake/home/Keymote')

    # This mock will make abspath return something outside the controlled 'root'
    mocker.patch('os.path.abspath', return_value='/fake/home/another_dir')

    response = client.get('/api/list_presentations?path=../another_dir')

    assert response.status_code == 403
    data = response.get_json()
    assert data['status'] == 'error'
    assert data['message'] == 'Access denied.'


def test_list_presentations_not_found(client, mocker):
    """
    Test the /api/list_presentations endpoint for a non-existent directory.
    """
    mocker.patch('os.path.expanduser', return_value='/fake/home')
    mocker.patch('os.path.abspath', side_effect=lambda x: x if x.startswith('/') else os.path.join('/fake/home', x))

    # Mock os.scandir to raise FileNotFoundError
    mocker.patch('os.scandir', side_effect=FileNotFoundError)

    response = client.get('/api/list_presentations?path=non_existent_dir')

    assert response.status_code == 404
    data = response.get_json()
    assert data['status'] == 'error'
    assert data['message'] == 'Directory not found.'


def test_open_presentation_success(client, mocker):
    """
    Test the /api/open_presentation endpoint for a successful opening of a presentation.
    """
    # Mock file system interactions
    mocker.patch('os.path.expanduser', return_value='/fake/home')
    mocker.patch('os.path.isabs', return_value=False)
    mocker.patch('os.path.abspath', side_effect=lambda x: os.path.join('/fake/home', x))
    mocker.patch('os.path.isfile', return_value=True)

    # Mock subprocess calls
    mock_subprocess_run = mocker.patch('subprocess.run')
    # This will be a bit complex as it's called multiple times with different expected outcomes
    # 1. Open presentation (no output needed)
    # 2. Get slide count
    # 3. Get current slide number
    mock_slide_count_result = MagicMock()
    mock_slide_count_result.stdout = '10'
    mock_current_slide_result = MagicMock()
    mock_current_slide_result.stdout = '1'
    
    mock_subprocess_run.side_effect = [
        MagicMock(returncode=0),  # open script
        mock_slide_count_result,  # count script
        mock_current_slide_result # current slide script
    ]

    # Mock file I/O for slide_timings.json
    initial_json = {
        "current_presentation_id": None,
        "presentations": {}
    }
    mock_read_data = json.dumps(initial_json)
    mocker.patch('builtins.open', mock_open(read_data=mock_read_data))

    # Make the request
    response = client.post('/api/open_presentation', json={'filename': 'presentations/my_deck.key'})

    # Assertions
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert data['current_slide_number'] == 1

    # Check that open was called to write the updated timings
    handle = open('static/slide_timings.json', 'r+')
    handle.seek.assert_called_once_with(0)

    # Reconstruct the full string written to the file from all write calls
    written_data = "".join(call.args[0] for call in handle.write.call_args_list)
    updated_json = json.loads(written_data)

    assert updated_json['current_presentation_id'] == 'presentations/my_deck.key'
    assert 'presentations/my_deck.key' in updated_json['presentations']
    assert len(updated_json['presentations']['presentations/my_deck.key']['slides']) == 10


def test_open_presentation_file_not_found(client, mocker):
    """
    Test /api/open_presentation when the requested file does not exist.
    """
    mocker.patch('os.path.expanduser', return_value='/fake/home')
    mocker.patch('os.path.isabs', return_value=False)
    mocker.patch('os.path.abspath', side_effect=lambda x: os.path.join('/fake/home', x))
    mocker.patch('os.path.isfile', return_value=False)  # Simulate file not existing

    response = client.post('/api/open_presentation', json={'filename': 'nonexistent.key'})

    assert response.status_code == 404
    data = response.get_json()
    assert data['status'] == 'error'
    assert "not found" in data['message']


def test_open_presentation_no_filename(client):
    """
    Test /api/open_presentation when no filename is provided in the request.
    """
    response = client.post('/api/open_presentation', json={})  # Empty JSON
    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'
    assert data['message'] == 'Filename not provided.'


def test_open_presentation_path_traversal(client, mocker):
    """
    Test /api/open_presentation against path traversal.
    """
    mocker.patch('os.path.expanduser', return_value='/fake/home/Keymote')
    # Simulate abspath resolving to a path outside the allowed root
    mocker.patch('os.path.abspath', return_value='/fake/home/another/secrets.key')

    response = client.post('/api/open_presentation', json={'filename': '../another/secrets.key'})

    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'
    assert 'Path traversal attempt' in data['message']


def test_open_presentation_absolute_path(client, mocker):
    """
    Test /api/open_presentation with an absolute path, which should be forbidden.
    """
    mocker.patch('os.path.isabs', return_value=True)
    response = client.post('/api/open_presentation', json={'filename': '/Users/someone/secrets.key'})
    assert response.status_code == 400
    data = response.get_json()
    assert data['status'] == 'error'
    assert 'Absolute paths are not allowed' in data['message']


def test_open_presentation_applescript_error(client, mocker):
    """
    Test /api/open_presentation when a subprocess call to AppleScript fails.
    """
    mocker.patch('os.path.expanduser', return_value='/fake/home')
    mocker.patch('os.path.isabs', return_value=False)
    mocker.patch('os.path.abspath', side_effect=lambda x: os.path.join('/fake/home', x))
    mocker.patch('os.path.isfile', return_value=True)

    # Mock subprocess to raise an error
    mocker.patch('subprocess.run', side_effect=subprocess.CalledProcessError(1, 'osascript', stderr="AppleScript Error"))

    response = client.post('/api/open_presentation', json={'filename': 'presentations/my_deck.key'})

    assert response.status_code == 500
    data = response.get_json()
    assert data['status'] == 'error'
    assert 'Failed to open or get info from presentation' in data['message'] 