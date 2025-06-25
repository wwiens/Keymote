// JavaScript moved from index.html

const socket = io();

const playPauseBtn = document.getElementById('play-pause-btn');
const playPauseIcon = document.getElementById('play-pause-icon');
const hoursEl = document.getElementById('main-time-hours');
const minutesEl = document.getElementById('main-time-minutes');
const secondsEl = document.getElementById('main-time-seconds');
const nextBtn = document.getElementById('next-btn');
const previousBtn = document.getElementById('previous-btn');
const slidesContainer = document.getElementById('slides-container');
const currentSlideNumberEl = document.getElementById('current-slide-number');
const totalSlideNumberEl = document.getElementById('total-slide-number');
const trackingDisplayEl = document.getElementById('tracking-display');
const slideInfoActiveEl = document.getElementById('slide-info-active');
const slideInfoInactiveEl = document.getElementById('slide-info-inactive');

// --- HAMBURGER MENU ---
const hamburgerMenu = document.getElementById('hamburger-menu');
const dropdownMenu = document.getElementById('dropdown-menu');

// --- FILE OPEN OVERLAY ELEMENTS ---
const openPresentationMenu = document.getElementById('open-presentation-menu');
const fileOpenOverlay = document.getElementById('file-open-overlay');
const fileListContainer = document.getElementById('file-list');
const cancelFileOpenBtn = document.getElementById('cancel-file-open');
const okFileOpenBtn = document.getElementById('ok-file-open');
const fileBrowserPathEl = document.getElementById('file-browser-path');
const fileBrowserBackBtn = document.getElementById('file-browser-back-btn');
const loadingOverlay = document.getElementById('loading-overlay');
const stopPresentationMenu = document.getElementById('stop-presentation-menu');
const closePresentationMenu = document.getElementById('close-presentation-menu');
let currentBrowserPath = '.';
let selectedFilePath = null;

// --- TIME EDIT OVERLAY ELEMENTS ---
const timeEditOverlay = document.getElementById('time-edit-overlay');
const minutesValueEl = document.getElementById('minutes-value');
const secondsValueEl = document.getElementById('seconds-value');
const minutesMinusBtn = document.getElementById('minutes-minus');
const minutesPlusBtn = document.getElementById('minutes-plus');
const secondsMinusBtn = document.getElementById('seconds-minus');
const secondsPlusBtn = document.getElementById('seconds-plus');
const saveTimeBtn = document.getElementById('save-time-edit');
const cancelTimeBtn = document.getElementById('cancel-time-edit');
let activeSlideIndex = -1; // To track which slide is being edited

let presentationsData = {};
let slideTimings = [];
let lastTrackingText = '0:00';

// --- GLOBAL UTILITY FUNCTIONS ---
function formatTime(secs) {
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

// --- SLIDE SELECTION FUNCTIONALITY ---
let currentSlideIdx = 0;
let totalSlides = 0;

function selectSlide(idx) {
  const slides = slidesContainer ? slidesContainer.querySelectorAll('.slide-progress') : [];
  if (!slides.length) return;
  // Clamp idx
  idx = Math.max(0, Math.min(idx, slides.length - 1));

  const slideNumber = idx + 1;
  fetch(`/api/goto_slide/${slideNumber}`, { method: 'POST' })
    .then(response => {
      if (!response.ok) {
        response.json().then(data => console.error(`Failed to go to slide ${slideNumber}:`, data.message));
      }
      // The websocket `slide_update` event will handle the UI update.
    })
    .catch(error => console.error(`Error calling goto_slide API for slide ${slideNumber}:`, error));
}

function showActiveSlideDisplay() {
    if (slideInfoActiveEl) slideInfoActiveEl.style.display = 'inline';
    if (slideInfoInactiveEl) slideInfoInactiveEl.style.display = 'none';
}

function showInactiveSlideDisplay() {
    if (slideInfoActiveEl) slideInfoActiveEl.style.display = 'none';
    if (slideInfoInactiveEl) slideInfoInactiveEl.style.display = 'inline';
}

function resetAllTimersAndTracking(trackingValue = '0:00') {
    elapsedSeconds = 0;
    lastTrackingText = trackingValue;
    updateMainTimeDisplay(0);
    // Optionally reset other timer-related UI here if needed
}

function resetHeaderForStoppedPresentation() {
    stopTimerAndResetButton();
    // Do not reset timers here; only update UI for stopped state
}

function resetHeaderToNoPresentationState() {
    stopTimerAndResetButton();
    elapsedSeconds = 0;
    updateMainTimeDisplay(elapsedSeconds); // Resets time to 0:00:00 and colors

    // Update total time and slide display
    const totalTimeEl = document.getElementById('total-time-display');
    if (totalTimeEl) totalTimeEl.textContent = '-';
    showInactiveSlideDisplay();

    // Clear the slide list and show a message
    if (slidesContainer) {
        slidesContainer.innerHTML = '<div class="empty-state-message">Open a presentation to begin.</div>';
        if (totalSlideNumberEl) totalSlideNumberEl.textContent = '0';
    }
}

function updateSelectedSlideUI(slideNumber) {
    if (!slideNumber) return;

    const idx = slideNumber - 1;

    const slides = slidesContainer ? slidesContainer.querySelectorAll('.slide-progress') : [];
    if (!slides.length || idx < 0 || idx >= slides.length) return;

    slides.forEach(slide => slide.classList.remove('slide-selected'));
    slides[idx].classList.add('slide-selected');
    if (currentSlideNumberEl) currentSlideNumberEl.textContent = (idx + 1).toString();
    currentSlideIdx = idx;
    slides[idx].scrollIntoView({ behavior: 'smooth', block: 'center' });
    updateMainTimeDisplay(elapsedSeconds);
}

function updatePresentationUI(data) {
    presentationsData = data;

    // First, check if a presentation is actually running
    fetch('/api/current_slide_number')
        .then(res => res.json())
        .then(api_data => {
            if (api_data.status === 'success' && api_data.slide_number) {
                // A presentation is active. Build the full UI.
                const currentPresentationId = presentationsData.current_presentation_id;
                const currentPresentation = presentationsData.presentations[currentPresentationId];
                if (!currentPresentation) {
                    resetHeaderToNoPresentationState();
                    return;
                }
                
                showActiveSlideDisplay();

                let cumulativeTime = 0;
                slideTimings = currentPresentation.slides.map(slide => {
                    cumulativeTime += slide.estimated_time_seconds || 0;
                    return { ...slide, cumulative_time_seconds: cumulativeTime };
                });

                const totalSeconds = slideTimings.reduce((sum, slide) => sum + (slide.estimated_time_seconds || 0), 0);
                const formatted = formatTime(totalSeconds);
                document.getElementById('total-time-display').textContent = formatted;

                if (slidesContainer) {
                    slidesContainer.innerHTML = '';
                    slideTimings.forEach((slide, idx) => {
                        const planned = formatMmSs(slide.estimated_time_seconds);
                        const slideDiv = document.createElement('div');
                        slideDiv.className = 'slide-progress editable-slide';
                        slideDiv.id = `slide-${slide.slide}`;
                        slideDiv.style.cursor = 'pointer';
                        slideDiv.innerHTML = `
                            <span class="slide-label">Slide <span class="slide-number">${slide.slide}</span></span>
                            <span class="progress-time editable-time"><span class="planned-time">${planned}</span></span>
                            <button class="edit-icon">
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                                    <path d="M11 4H4C2.89543 4 2 4.89543 2 6V18C2 19.1046 2.89543 20 4 20H16C17.1046 20 18 19.1046 18 18V11M18.5 2.5C19.3284 1.67157 20.6716 1.67157 21.5 2.5C22.3284 3.32843 22.3284 4.67157 21.5 5.5L12 15L8 16L9 12L18.5 2.5Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
                                </svg>
                            </button>
                        `;
                        slideDiv.querySelector('.edit-icon').addEventListener('click', (e) => {
                            e.stopPropagation();
                            openTimeEditor(idx);
                        });
                        slidesContainer.appendChild(slideDiv);
                    });
                    addSlideClickListeners();
                }
                if (totalSlideNumberEl) totalSlideNumberEl.textContent = slideTimings.length;

                updateSelectedSlideUI(api_data.slide_number);

            } else {
                // No presentation is active.
                resetHeaderToNoPresentationState();
            }
        }).catch(() => {
            resetHeaderToNoPresentationState();
        });
}

function updateSlideListFromData(data) {
    if (!data || !data.presentations || !data.current_presentation_id) return;
    
    const currentPresentation = data.presentations[data.current_presentation_id];
    if (!currentPresentation || !currentPresentation.slides) return;
    
    slideTimings = currentPresentation.slides; // Update global slideTimings

    if (slidesContainer) {
        slidesContainer.innerHTML = '';
        slideTimings.forEach((slide, idx) => {
            const planned = formatMmSs(slide.estimated_time_seconds);
            const slideDiv = document.createElement('div');
            slideDiv.className = 'slide-progress editable-slide';
            slideDiv.id = `slide-${slide.slide}`;
            slideDiv.style.cursor = 'pointer';
            slideDiv.innerHTML = `
                <span class="slide-label">Slide <span class="slide-number">${slide.slide}</span></span>
                <span class="progress-time editable-time"><span class="planned-time">${planned}</span></span>
                <button class="edit-icon">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                        <path d="M11 4H4C2.89543 4 2 4.89543 2 6V18C2 19.1046 2.89543 20 4 20H16C17.1046 20 18 19.1046 18 18V11M18.5 2.5C19.3284 1.67157 20.6716 1.67157 21.5 2.5C22.3284 3.32843 22.3284 4.67157 21.5 5.5L12 15L8 16L9 12L18.5 2.5Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
                    </svg>
                </button>
            `;
            slideDiv.querySelector('.edit-icon').addEventListener('click', (e) => {
                e.stopPropagation();
                openTimeEditor(idx);
            });
            slidesContainer.appendChild(slideDiv);
        });
        addSlideClickListeners();
    }
    if (totalSlideNumberEl) totalSlideNumberEl.textContent = slideTimings.length;
}

document.addEventListener('DOMContentLoaded', function() {
  // Hamburger Menu Toggle
  if (hamburgerMenu) {
    hamburgerMenu.addEventListener('click', (event) => {
      event.stopPropagation();
      dropdownMenu.classList.toggle('show');
      hamburgerMenu.classList.toggle('active');
    });
  }

  // Close dropdown when clicking outside
  document.addEventListener('click', (event) => {
    if (dropdownMenu && dropdownMenu.classList.contains('show') && !hamburgerMenu.contains(event.target) && !dropdownMenu.contains(event.target)) {
        dropdownMenu.classList.remove('show');
        hamburgerMenu.classList.remove('active');
    }
  });

  if (openPresentationMenu) {
    openPresentationMenu.addEventListener('click', () => {
      openFileOpenOverlay();
      if (dropdownMenu) dropdownMenu.classList.remove('show');
      if (hamburgerMenu) hamburgerMenu.classList.remove('active');
    });
  }

  if (cancelFileOpenBtn) {
    cancelFileOpenBtn.addEventListener('click', closeFileOpenOverlay);
  }

  if (okFileOpenBtn) {
    okFileOpenBtn.addEventListener('click', () => {
        if (selectedFilePath) {
            openPresentation(selectedFilePath);
        }
    });
  }

  if (fileBrowserBackBtn) {
    fileBrowserBackBtn.addEventListener('click', () => {
      if (currentBrowserPath && currentBrowserPath !== '.') {
        const parentPath = currentBrowserPath.substring(0, currentBrowserPath.lastIndexOf('/')) || '.';
        browseDirectory(parentPath);
      }
    });
  }

  if (stopPresentationMenu) {
    stopPresentationMenu.addEventListener('click', () => {
        fetch('/api/stop_presentation', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.status !== 'success') {
                    console.error('Failed to stop presentation:', data.message);
                } else {
                    stopTimerAndResetButton();
                    resetAllTimersAndTracking(); // Reset both elapsed and tracking timers to 0
                }
                // The websocket event 'presentation_stopped' will handle the UI update.
            })
            .catch(err => console.error('Error stopping presentation:', err));
        if (dropdownMenu) dropdownMenu.classList.remove('show');
        if (hamburgerMenu) hamburgerMenu.classList.remove('active');
    });
  }

  if (closePresentationMenu) {
    closePresentationMenu.addEventListener('click', () => {
        fetch('/api/close_presentation', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.status !== 'success') {
                    console.error('Failed to close presentation:', data.message);
                }
                // The websocket event 'presentation_closed' will handle the UI update.
            })
            .catch(err => console.error('Error closing presentation:', err));
        if (dropdownMenu) dropdownMenu.classList.remove('show');
        if (hamburgerMenu) hamburgerMenu.classList.remove('active');
    });
  }

  socket.on('slide_update', function(data) {
    if (data.slide_number) {
        console.log('Received slide update:', data.slide_number);
        updateSelectedSlideUI(data.slide_number);
    }
  });

  socket.on('presentation_closed', function() {
    console.log('Received presentation closed event.');
    resetAllTimersAndTracking('-');
    resetHeaderToNoPresentationState();
  });

  socket.on('presentation_stopped', function() {
    console.log('Received presentation stopped event.');
    resetHeaderForStoppedPresentation();
  });

  fetch('static/slide_timings.json')
    .then(response => response.json())
    .then(data => {
      updatePresentationUI(data);
      addSlideClickListeners();
    })
    .catch(err => {
      console.error('Could not load slide timings:', err);
    });

  // Initialize display on load
  updateMainTimeDisplay(elapsedSeconds);
});

// --- TIMER FUNCTIONALITY ---
let timerInterval = null;
let elapsedSeconds = 0;
let timerRunning = false;

function updateMainTimeDisplay(secs) {
  const h = Math.floor(secs / 3600).toString();
  const m = Math.floor((secs % 3600) / 60).toString().padStart(2, '0');
  const s = (secs % 60).toString().padStart(2, '0');
  if (hoursEl) hoursEl.textContent = h;
  if (minutesEl) minutesEl.textContent = m;
  if (secondsEl) secondsEl.textContent = s;

  if (trackingDisplayEl) {
    if (slideTimings.length > 0 && currentSlideIdx < slideTimings.length && currentSlideIdx >= 0) {
      const plannedTime = slideTimings[currentSlideIdx].cumulative_time_seconds;
      const difference = plannedTime - secs;
      const formatDifference = (diffSecs) => {
        const absoluteSeconds = Math.abs(Math.trunc(diffSecs));
        const minutes = Math.floor(absoluteSeconds / 60);
        const seconds = absoluteSeconds % 60;
        return `${minutes}:${seconds.toString().padStart(2, '0')}`;
      };
      let trackingText = '0:00';
      if (difference <= -1) {
        trackingText = `-${formatDifference(difference)}`;
        trackingDisplayEl.style.color = '#ea4335'; // Red
        if (minutesEl) minutesEl.style.color = '#ea4335';
      } else if (difference >= 1) {
        trackingText = `+${formatDifference(difference)}`;
        trackingDisplayEl.style.color = '#34a853'; // Green
        if (minutesEl) minutesEl.style.color = '#34a853';
      } else {
        trackingText = '0:00';
        trackingDisplayEl.style.color = 'inherit';
        if (minutesEl) minutesEl.style.color = 'inherit';
      }
      if (timerRunning) {
        trackingDisplayEl.textContent = trackingText;
        lastTrackingText = trackingText;
      } else {
        trackingDisplayEl.textContent = lastTrackingText;
      }
    } else {
      trackingDisplayEl.textContent = lastTrackingText;
      trackingDisplayEl.style.color = 'inherit';
      if (minutesEl) minutesEl.style.color = 'inherit';
    }
  }
}

function pauseTimer() {
    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
    timerRunning = false;
    if (playPauseIcon) playPauseIcon.src = 'static/images/008-play-button.png';
    showInactiveSlideDisplay(); // Exit presentation mode UI
    updateMainTimeDisplay(elapsedSeconds); // Show frozen values
    // Also stop Keynote presentation mode on the server
    fetch('/api/stop_presentation', { method: 'POST' })
        .then(response => {
            if (!response.ok) {
                response.json().then(data => console.error('Failed to stop presentation:', data.message));
            }
        })
        .catch(error => console.error('Error calling stop_presentation API:', error));
}

if (playPauseBtn) {
  playPauseBtn.addEventListener('click', function() {
    if (timerRunning) {
      pauseTimer();
    } else {
      startTimer();
    }
  });
}

// --- Patch next/previous button logic ---
if (nextBtn) {
  nextBtn.addEventListener('click', function() {
    fetch('/api/next_slide', { method: 'POST' })
      .then(response => {
        if (!response.ok) {
          response.json().then(data => console.error('Failed to move to next slide:', data.message));
        }
        // UI will be updated by the websocket event
      })
      .catch(error => console.error('Error calling next_slide API:', error));
  });
}
if (previousBtn) {
  previousBtn.addEventListener('click', function() {
    fetch('/api/previous_slide', { method: 'POST' })
      .then(response => {
        if (!response.ok) {
          response.json().then(data => console.error('Failed to move to previous slide:', data.message));
        }
        // UI will be updated by the websocket event
      })
      .catch(error => console.error('Error calling previous_slide API:', error));
  });
}

// --- Patch slide click listeners ---
function addSlideClickListeners() {
  const slides = slidesContainer ? slidesContainer.querySelectorAll('.slide-progress') : [];
  slides.forEach((slide, idx) => {
    slide.onclick = () => selectSlide(idx);
  });
}

// --- After slides are loaded, store timings and patch select ---
function trySelectFirstSlide() {
  const slides = slidesContainer ? slidesContainer.querySelectorAll('.slide-progress') : [];
  if (slides.length) {
    totalSlides = slides.length;
    if (totalSlideNumberEl) totalSlideNumberEl.textContent = totalSlides;

    // On initial load, just update the UI, don't trigger a navigation.
    const firstSlideIdx = 0;
    slides[firstSlideIdx].classList.add('slide-selected');
    if (currentSlideNumberEl) currentSlideNumberEl.textContent = (firstSlideIdx + 1).toString();
    currentSlideIdx = firstSlideIdx;

    addSlideClickListeners();
  }
}

// Wait for slides to be loaded (since they're loaded async)
const observer = new MutationObserver(trySelectFirstSlide);
if (slidesContainer) {
  observer.observe(slidesContainer, {childList: true});
}

function startTimer() {
  if (timerInterval) return;

  fetch('/api/start_presentation', { method: 'POST' })
    .then(response => {
      if (!response.ok) {
        response.json().then(data => console.error('Failed to start presentation:', data.message));
      }
    })
    .catch(error => console.error('Error calling start_presentation API:', error));

  // Check current slide number on play
  fetch('/api/current_slide_number')
    .then(response => response.json())
    .then(data => {
      if (data.slide_number) {
        // The server sends a 1-based slide number.
        const idx = data.slide_number - 1;
        const slides = slidesContainer ? slidesContainer.querySelectorAll('.slide-progress') : [];
        if (slides.length > idx) {
            // Update UI without triggering another API call
            slides.forEach(slide => slide.classList.remove('slide-selected'));
            slides[idx].classList.add('slide-selected');
            if (currentSlideNumberEl) currentSlideNumberEl.textContent = (idx + 1).toString();
            currentSlideIdx = idx;
            slides[idx].scrollIntoView({behavior: 'smooth', block: 'center'});
            updateMainTimeDisplay(elapsedSeconds);
        }
      }
    })
    .catch(error => console.error('Error getting current slide number:', error));

  timerInterval = setInterval(() => {
    elapsedSeconds++;
    updateMainTimeDisplay(elapsedSeconds);
  }, 1000);
  timerRunning = true;
  if (playPauseIcon) playPauseIcon.src = 'static/images/009-pause-button.png';
}

// --- TIME EDIT OVERLAY FUNCTIONS ---

function formatMmSs(secs) {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function openTimeEditor(slideIndex) {
  activeSlideIndex = slideIndex;
  const currentSeconds = slideTimings[slideIndex].estimated_time_seconds || 0;
  const minutes = Math.floor(currentSeconds / 60);
  const seconds = currentSeconds % 60;

  minutesValueEl.textContent = minutes.toString().padStart(2, '0');
  secondsValueEl.textContent = seconds.toString().padStart(2, '0');

  timeEditOverlay.style.display = 'flex';
}

function closeTimeEditor() {
  timeEditOverlay.style.display = 'none';
}

function saveTime() {
  const minutes = parseInt(minutesValueEl.textContent, 10);
  const seconds = parseInt(secondsValueEl.textContent, 10);
  const newTotalSeconds = minutes * 60 + seconds;

  if (activeSlideIndex === -1 || isNaN(newTotalSeconds)) {
    console.error("Invalid slide index or time value");
    return;
  }
  
  // Update local slideTimings array
  slideTimings[activeSlideIndex].estimated_time_seconds = newTotalSeconds;

  // Recalculate cumulative times
  let cumulativeTime = 0;
  slideTimings = slideTimings.map(slide => {
      cumulativeTime += slide.estimated_time_seconds || 0;
      return { ...slide, cumulative_time_seconds: cumulativeTime };
  });

  // Update total time display
  totalPresentationSeconds = cumulativeTime;
  const el = document.getElementById('total-time-display');
  if (el) el.textContent = formatTime(totalPresentationSeconds);
  
  // Update the UI for the specific slide
  const slideElement = document.getElementById(`slide-${slideTimings[activeSlideIndex].slide}`);
  if (slideElement) {
    const plannedTimeEl = slideElement.querySelector('.planned-time');
    if (plannedTimeEl) {
      plannedTimeEl.textContent = formatMmSs(newTotalSeconds);
    }
  }

  // Prepare data for saving
  const dataToSave = JSON.parse(JSON.stringify(presentationsData));
  const currentPresentationId = dataToSave.current_presentation_id;
  
  // Update slides for the current presentation, removing cumulative_time_seconds
  dataToSave.presentations[currentPresentationId].slides = slideTimings.map(({ cumulative_time_seconds, ...slide }) => slide);

  // Persist changes to the server
  fetch('/api/save_timings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(dataToSave)
  }).catch(err => console.error('Error saving timings:', err));

  closeTimeEditor();
}

// Event Listeners for Time Edit Overlay
cancelTimeBtn.addEventListener('click', closeTimeEditor);
saveTimeBtn.addEventListener('click', saveTime);

minutesMinusBtn.addEventListener('click', () => {
  let minutes = parseInt(minutesValueEl.textContent, 10);
  if (minutes > 0) {
    minutes--;
    minutesValueEl.textContent = minutes.toString().padStart(2, '0');
  }
});

minutesPlusBtn.addEventListener('click', () => {
  let minutes = parseInt(minutesValueEl.textContent, 10);
  if (minutes < 59) { // Cap at 59, can be changed
    minutes++;
    minutesValueEl.textContent = minutes.toString().padStart(2, '0');
  }
});

secondsMinusBtn.addEventListener('click', () => {
  let seconds = parseInt(secondsValueEl.textContent, 10);
  seconds = (seconds - 10 + 60) % 60;
  secondsValueEl.textContent = seconds.toString().padStart(2, '0');
});

secondsPlusBtn.addEventListener('click', () => {
  let seconds = parseInt(secondsValueEl.textContent, 10);
  seconds = (seconds + 10) % 60;
  secondsValueEl.textContent = seconds.toString().padStart(2, '0');
});

// --- FILE OPEN FUNCTIONALITY ---
function browseDirectory(path) {
  currentBrowserPath = path;
  selectedFilePath = null; // Reset selection when changing directories
  okFileOpenBtn.disabled = true;
  fileListContainer.innerHTML = '<div class="file-item-none">Loading...</div>';

  fetch(`/api/list_presentations?path=${encodeURIComponent(path)}`)
    .then(response => {
        if (!response.ok) { throw new Error('Network response was not ok.'); }
        return response.json();
    })
    .then(data => {
        if (data.status === 'success') {
            fileListContainer.innerHTML = ''; // Clear loading/previous list
            
            // Update UI elements
            fileBrowserPathEl.textContent = `/${data.path || ''}`;
            fileBrowserBackBtn.disabled = !data.path; // Disable back button at root

            if (data.items.length > 0) {
                data.items.forEach(item => {
                    const fileItem = document.createElement('div');
                    fileItem.className = 'file-item ' + item.type;
                    fileItem.textContent = item.name;
                    
                    fileItem.addEventListener('click', () => {
                        if (item.type === 'directory') {
                            browseDirectory(item.path);
                        } else {
                            // Visually select the file
                            const allItems = fileListContainer.querySelectorAll('.file-item');
                            allItems.forEach(el => el.classList.remove('selected'));
                            fileItem.classList.add('selected');
                            selectedFilePath = item.path;
                            okFileOpenBtn.disabled = false;
                        }
                    });
                    fileListContainer.appendChild(fileItem);
                });
            } else {
                fileListContainer.innerHTML = '<div class="file-item-none">This folder is empty.</div>';
            }
        } else {
            throw new Error(data.message || 'Failed to list files.');
        }
    })
    .catch(error => {
        console.error('Error browsing directory:', error);
        fileListContainer.innerHTML = `<div class="file-item-none">Error: ${error.message}</div>`;
    });
}

function openFileOpenOverlay() {
  browseDirectory('.'); // Start at the root
  if (fileOpenOverlay) {
    fileOpenOverlay.style.display = 'flex';
  }
}

function closeFileOpenOverlay() {
  if (fileOpenOverlay) {
    fileOpenOverlay.style.display = 'none';
  }
}

function openPresentation(filename) {
  closeFileOpenOverlay();
  loadingOverlay.style.display = 'flex';

  fetch('/api/open_presentation', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename: filename }),
  })
    .then(response => response.json())
    .then(data => {
      if (data.status === 'success') {
        // If the backend provides the current slide number, highlight it immediately
        if (typeof data.current_slide_number === 'number' && data.current_slide_number > 0) {
          // Wait for the slide list to be loaded, then highlight
          fetch('static/slide_timings.json?t=' + new Date().getTime()) // Cache-bust
            .then(response => response.json())
            .then(timingsData => {
              updatePresentationUI(timingsData);
              // Highlight the correct slide after UI is built
              setTimeout(() => {
                updateSelectedSlideUI(data.current_slide_number);
              }, 100);
            })
            .catch(err => console.error('Failed to reload slide timings:', err));
        } else {
          // Fallback: just update UI as before
          fetch('static/slide_timings.json?t=' + new Date().getTime())
            .then(response => response.json())
            .then(updatePresentationUI)
            .catch(err => console.error('Failed to reload slide timings:', err));
        }
      } else {
        throw new Error(data.message || 'Failed to open presentation.');
      }
    })
    .catch(error => {
      console.error('Error opening presentation:', error);
      alert(`Error: ${error.message}`);
    })
    .finally(() => {
        loadingOverlay.style.display = 'none';
    });
}

function stopTimerAndResetButton() {
    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
    timerRunning = false;
    if (playPauseIcon) playPauseIcon.src = 'static/images/008-play-button.png';
    // Exit presentation mode UI if needed
} 