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

// --- EDIT TIME OVERLAY ELEMENTS ---
const editTimeOverlay = document.getElementById('edit-time-overlay');
const editElapsedTimeMenu = document.getElementById('edit-elapsed-time-menu');
const cancelEditTimeBtn = document.getElementById('cancel-edit-time');
const saveEditTimeBtn = document.getElementById('save-edit-time');
const editHoursInput = document.getElementById('edit-hours');
const editMinutesInput = document.getElementById('edit-minutes');
const editSecondsInput = document.getElementById('edit-seconds');

// --- FILE OPEN OVERLAY ELEMENTS ---
const openPresentationMenu = document.getElementById('open-presentation-menu');
const addBreakMenu = document.getElementById('add-break-menu');
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

// --- INLINE TIME EDITING ---
let editingSlideIndex = -1; // To track which slide is being edited

let presentationsData = {};
let slideTimings = [];
let lastTrackingText = '0:00';
let isPlayMode = false; // Track if presentation is in play mode

// --- GLOBAL UTILITY FUNCTIONS ---
function formatTime(secs) {
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function saveElapsedTimeToBackend(seconds) {
    fetch('/api/save_elapsed_time', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ elapsed_seconds: seconds }),
    })
    .then(response => response.json())
    .then(data => {
        if (data.status !== 'success') {
            console.error('Failed to save elapsed time:', data.message);
        }
    })
    .catch(error => console.error('Error saving elapsed time:', error));
}

// --- SLIDE SELECTION FUNCTIONALITY ---
let currentSlideIdx = 0;
let totalSlides = 0;

function selectSlide(idx) {
  const slides = slidesContainer ? slidesContainer.querySelectorAll('.slide-progress') : [];
  if (!slides.length) return;
  // Clamp idx
  idx = Math.max(0, Math.min(idx, slides.length - 1));

  // Check if the selected slide is a break
  if (slideTimings && slideTimings[idx] && slideTimings[idx].slide === 'BREAK') {
    // For breaks, just update the UI selection without calling Keynote API
    updateSelectedSlideByIndex(idx);
    return;
  }

  // Calculate the actual Keynote slide number by counting non-break slides up to this index
  let keynoteSlideNumber = 0;
  for (let i = 0; i <= idx && i < slideTimings.length; i++) {
    if (slideTimings[i].slide !== 'BREAK') {
      keynoteSlideNumber++;
    }
  }

  if (keynoteSlideNumber > 0) {
    fetch(`/api/goto_slide/${keynoteSlideNumber}`, { method: 'POST' })
      .then(response => {
        if (!response.ok) {
          response.json().then(data => console.error(`Failed to go to slide ${keynoteSlideNumber}:`, data.message));
        }
        // The websocket `slide_update` event will handle the UI update for regular slides
      })
      .catch(error => console.error(`Error calling goto_slide API for slide ${keynoteSlideNumber}:`, error));
  }
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
    if (trackingDisplayEl) trackingDisplayEl.textContent = '-';
    const timeLeftEl = document.getElementById('time-left-display');
    if (timeLeftEl) timeLeftEl.textContent = '-';
    showInactiveSlideDisplay();

    // Clear the slide list and show a message
    if (slidesContainer) {
        slidesContainer.innerHTML = '<div class="empty-state-message">Open a presentation to begin.</div>';
        if (totalSlideNumberEl) totalSlideNumberEl.textContent = '0';
    }
}

function updateSelectedSlideUI(slideNumber) {
    if (!slideNumber) return;

    // Map Keynote slide number to our internal index (accounting for breaks)
    let keynoteSlideCount = 0;
    let idx = -1;
    
    for (let i = 0; i < slideTimings.length; i++) {
        if (slideTimings[i].slide !== 'BREAK') {
            keynoteSlideCount++;
            if (keynoteSlideCount === slideNumber) {
                idx = i;
                break;
            }
        }
    }
    
    if (idx === -1) return; // Slide not found
    
    updateSelectedSlideByIndex(idx);
}

function updateSelectedSlideByIndex(idx) {
    if (!slideTimings || idx < 0 || idx >= slideTimings.length) return;

    const slides = slidesContainer ? slidesContainer.querySelectorAll('.slide-progress') : [];
    if (!slides.length || idx >= slides.length) return;

    slides.forEach(slide => slide.classList.remove('slide-selected'));
    slides[idx].classList.add('slide-selected');
    
    // Update display - show either slide number or "BREAK"
    if (slideTimings[idx].slide === 'BREAK') {
        if (currentSlideNumberEl) currentSlideNumberEl.textContent = 'BREAK';
    } else {
        // Calculate the display slide number for regular slides
        let slideDisplayNumber = 0;
        for (let i = 0; i <= idx; i++) {
            if (slideTimings[i].slide !== 'BREAK') {
                slideDisplayNumber++;
            }
        }
        if (currentSlideNumberEl) currentSlideNumberEl.textContent = slideDisplayNumber.toString();
    }
    
    currentSlideIdx = idx;
    slides[idx].scrollIntoView({ behavior: 'smooth', block: 'center' });
    updateMainTimeDisplay(elapsedSeconds);
    updateTimeLeftDisplay();
    // Only start per-slide timer if in play mode
    if (isPlayMode) {
      startSlideTimer(idx);
    } else {
      stopSlideTimer();
    }
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
                    clearStuckEditingStates(); // Clear any stuck editing states
                    slideTimings.forEach((slide, idx) => {
                        const slideDiv = document.createElement('div');
                        slideDiv.className = slide.slide === 'BREAK' ? 'slide-progress editable-slide break-slide' : 'slide-progress editable-slide';
                        slideDiv.id = `slide-${slide.slide}`;
                        slideDiv.style.cursor = 'pointer';
                        
                        // Different HTML for break vs regular slide
                        if (slide.slide === 'BREAK') {
                            slideDiv.innerHTML = `
                                <span class="slide-label break-label">BREAK <span class="slide-elapsed">0:00 of <span class="time-value" data-slide-index="${idx}">${formatMmSs(slide.estimated_time_seconds)}</span></span></span>
                                <div class="slide-controls">
                                    <button class="edit-icon" data-slide-index="${idx}" title="Edit break duration">
                                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                                            <path d="M11 4H4C2.89543 4 2 4.89543 2 6V18C2 19.1046 2.89543 20 4 20H16C17.1046 20 18 19.1046 18 18V11M18.5 2.5C19.3284 1.67157 20.6716 1.67157 21.5 2.5C22.3284 3.32843 22.3284 4.67157 21.5 5.5L12 15L8 16L9 12L18.5 2.5Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
                                        </svg>
                                    </button>
                                    <button class="delete-icon" data-slide-index="${idx}" title="Delete break">
                                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                                            <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6h14zM10 11v6M14 11v6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
                                        </svg>
                                    </button>
                                </div>
                            `;
                        } else {
                            slideDiv.innerHTML = `
                                <span class="slide-label">Slide <span class="slide-number">${slide.slide}</span> <span class="slide-elapsed">0:00 of <span class="time-value" data-slide-index="${idx}">${formatMmSs(slide.estimated_time_seconds)}</span></span></span>
                                <button class="edit-icon" data-slide-index="${idx}" title="Edit slide duration">
                                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                                        <path d="M11 4H4C2.89543 4 2 4.89543 2 6V18C2 19.1046 2.89543 20 4 20H16C17.1046 20 18 19.1046 18 18V11M18.5 2.5C19.3284 1.67157 20.6716 1.67157 21.5 2.5C22.3284 3.32843 22.3284 4.67157 21.5 5.5L12 15L8 16L9 12L18.5 2.5Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
                                    </svg>
                                </button>
                            `;
                        }
                        
                        // Add event listener for the edit icon
                        const editIcon = slideDiv.querySelector('.edit-icon');
                        editIcon.addEventListener('click', (e) => {
                            e.stopPropagation();
                            startEditingTime(idx);
                        });
                        
                        // Add event listener for the delete icon (only for break slides)
                        const deleteIcon = slideDiv.querySelector('.delete-icon');
                        if (deleteIcon) {
                            deleteIcon.addEventListener('click', (e) => {
                                e.stopPropagation();
                                deleteBreakSlide(idx);
                            });
                        }
                        
                        slidesContainer.appendChild(slideDiv);
                    });
                    addSlideClickListeners();
                }
                if (totalSlideNumberEl) totalSlideNumberEl.textContent = slideTimings.length;

                updateSelectedSlideUI(api_data.slide_number);
                updateSlideTimersUI();
                updateTimeLeftDisplay();

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
        clearStuckEditingStates(); // Clear any stuck editing states
        slideTimings.forEach((slide, idx) => {
            const slideDiv = document.createElement('div');
            slideDiv.className = slide.slide === 'BREAK' ? 'slide-progress editable-slide break-slide' : 'slide-progress editable-slide';
            slideDiv.id = `slide-${slide.slide}`;
            slideDiv.style.cursor = 'pointer';
            
            // Different HTML for break vs regular slide
            if (slide.slide === 'BREAK') {
                slideDiv.innerHTML = `
                    <span class="slide-label break-label">BREAK <span class="slide-elapsed">0:00 of <span class="time-value" data-slide-index="${idx}">${formatMmSs(slide.estimated_time_seconds)}</span></span></span>
                    <div class="slide-controls">
                        <button class="edit-icon" data-slide-index="${idx}" title="Edit break duration">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                                <path d="M11 4H4C2.89543 4 2 4.89543 2 6V18C2 19.1046 2.89543 20 4 20H16C17.1046 20 18 19.1046 18 18V11M18.5 2.5C19.3284 1.67157 20.6716 1.67157 21.5 2.5C22.3284 3.32843 22.3284 4.67157 21.5 5.5L12 15L8 16L9 12L18.5 2.5Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
                            </svg>
                        </button>
                        <button class="delete-icon" data-slide-index="${idx}" title="Delete break">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                                <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6h14zM10 11v6M14 11v6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
                            </svg>
                        </button>
                    </div>
                `;
            } else {
                slideDiv.innerHTML = `
                    <span class="slide-label">Slide <span class="slide-number">${slide.slide}</span> <span class="slide-elapsed">0:00 of <span class="time-value" data-slide-index="${idx}">${formatMmSs(slide.estimated_time_seconds)}</span></span></span>
                    <button class="edit-icon" data-slide-index="${idx}" title="Edit slide duration">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                            <path d="M11 4H4C2.89543 4 2 4.89543 2 6V18C2 19.1046 2.89543 20 4 20H16C17.1046 20 18 19.1046 18 18V11M18.5 2.5C19.3284 1.67157 20.6716 1.67157 21.5 2.5C22.3284 3.32843 22.3284 4.67157 21.5 5.5L12 15L8 16L9 12L18.5 2.5Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
                        </svg>
                    </button>
                `;
            }
            
            // Add event listener for the edit icon
            const editIcon = slideDiv.querySelector('.edit-icon');
            editIcon.addEventListener('click', (e) => {
                e.stopPropagation();
                startEditingTime(idx);
            });
            
            // Add event listener for the delete icon (only for break slides)
            const deleteIcon = slideDiv.querySelector('.delete-icon');
            if (deleteIcon) {
                deleteIcon.addEventListener('click', (e) => {
                    e.stopPropagation();
                    deleteBreakSlide(idx);
                });
            }
            
            slidesContainer.appendChild(slideDiv);
        });
        addSlideClickListeners();
    }
    if (totalSlideNumberEl) totalSlideNumberEl.textContent = slideTimings.length;
    updateSlideTimersUI();
    updateTimeLeftDisplay();
}

function setupEventListeners() {
    // Hamburger Menu
    if (hamburgerMenu) {
        hamburgerMenu.addEventListener('click', (event) => {
            event.stopPropagation(); // Prevent the document click from closing it immediately
            if (dropdownMenu) dropdownMenu.classList.toggle('show');
            hamburgerMenu.classList.toggle('active');
        });
    }

    // Close dropdown when clicking outside
    document.addEventListener('click', (event) => {
        if (dropdownMenu && dropdownMenu.classList.contains('show') && !hamburgerMenu.contains(event.target) && !dropdownMenu.contains(event.target)) {
            dropdownMenu.classList.remove('show');
            if (hamburgerMenu) hamburgerMenu.classList.remove('active');
        }
    });

    // Main Controls
    if (playPauseBtn) {
        playPauseBtn.addEventListener('click', () => {
            if (isPlayMode) {
                pauseTimer();
            } else {
                startTimer();
            }
        });
    }
    if (nextBtn) nextBtn.addEventListener('click', navigateToNextSlide);
    if (previousBtn) previousBtn.addEventListener('click', navigateToPreviousSlide);

    // File Open Overlay
    if (openPresentationMenu) {
        openPresentationMenu.addEventListener('click', () => {
            openFileOpenOverlay();
            if (dropdownMenu) dropdownMenu.classList.remove('active');
        });
    }
    if (cancelFileOpenBtn) cancelFileOpenBtn.addEventListener('click', closeFileOpenOverlay);
    if (okFileOpenBtn) {
        okFileOpenBtn.addEventListener('click', () => {
            if (selectedFilePath) {
                openPresentation(selectedFilePath);
            }
        });
    }
    if (fileBrowserBackBtn) {
        fileBrowserBackBtn.addEventListener('click', () => {
            const parentDir = currentBrowserPath.substring(0, currentBrowserPath.lastIndexOf('/')) || '.';
            browseDirectory(parentDir);
        });
    }
    
    // Presentation Actions
    if (addBreakMenu) {
        addBreakMenu.addEventListener('click', () => {
            addBreakAfterCurrentSlide();
            if (dropdownMenu) dropdownMenu.classList.remove('active');
        });
    }
    if (stopPresentationMenu) {
        stopPresentationMenu.addEventListener('click', () => {
            fetch('/api/stop_presentation', { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    if (data.status === 'success') {
                        console.log("Presentation stopped successfully from menu.");
                        resetHeaderForStoppedPresentation();
                    } else {
                        console.error("Failed to stop presentation:", data.message);
                    }
                });
            if (dropdownMenu) dropdownMenu.classList.remove('active');
        });
    }
    if (closePresentationMenu) {
        closePresentationMenu.addEventListener('click', () => {
            fetch('/api/close_presentation', { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    if (data.status === 'success') {
                        console.log("Presentation closed successfully from menu.");
                        resetHeaderToNoPresentationState();
                    } else {
                        console.error("Failed to close presentation:", data.message);
                    }
                });
            if (dropdownMenu) dropdownMenu.classList.remove('active');
        });
    }

    // Edit Time Overlay
    if (editElapsedTimeMenu) {
        editElapsedTimeMenu.addEventListener('click', () => {
            openEditTimeOverlay();
            if (dropdownMenu) dropdownMenu.classList.remove('active');
        });
    }
    if (cancelEditTimeBtn) {
        cancelEditTimeBtn.addEventListener('click', closeEditTimeOverlay);
    }
    if (saveEditTimeBtn) {
        saveEditTimeBtn.addEventListener('click', saveEditedTime);
    }

    // Keyboard Shortcuts
    document.addEventListener('keydown', (event) => {
        if (event.target.tagName === 'INPUT') return; // Ignore when typing in inputs

        switch (event.key) {
            case 'ArrowRight':
                navigateToNextSlide();
                break;
            case 'ArrowLeft':
                navigateToPreviousSlide();
                break;
            case ' ': // Space bar
                event.preventDefault(); // Prevent page scroll
                if (isPlayMode) {
                    pauseTimer();
                } else {
                    startTimer();
                }
                break;
        }
    });
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
        if (hamburgerMenu) hamburgerMenu.classList.remove('active');
    }
  });

  if (openPresentationMenu) {
      openPresentationMenu.addEventListener('click', () => {
          openFileOpenOverlay();
      if (dropdownMenu) dropdownMenu.classList.remove('show');
      if (hamburgerMenu) hamburgerMenu.classList.remove('active');
      });
  }

  if (addBreakMenu) {
    addBreakMenu.addEventListener('click', () => {
      addBreakAfterCurrentSlide();
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
          // Send request to server to stop presentation
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
        // Send request to server to close presentation
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
        // Only start the slide timer if in play mode
        if (isPlayMode) {
          startSlideTimer(data.slide_number - 1);
        } else {
          stopSlideTimer();
        }
    }
  });

  socket.on('presentation_closed', function() {
    console.log('Received presentation closed event.');
    isPlayMode = false;
    resetAllTimersAndTracking('-');
    resetHeaderToNoPresentationState();
    stopSlideTimer();
  });

  socket.on('presentation_stopped', function() {
    console.log('Received presentation stopped event.');
    isPlayMode = false;
    resetHeaderForStoppedPresentation();
    stopSlideTimer();
  });

  socket.on('presentation_started', function() {
    console.log('Received presentation started event.');
    isPlayMode = true;
    // Start timers for the current slide
    if (typeof currentSlideIdx === 'number' && currentSlideIdx >= 0) {
      startSlideTimer(currentSlideIdx);
    }
  });

  fetch('static/slide_timings.json')
    .then(response => response.json())
    .then(data => {
      updatePresentationUI(data);
      addSlideClickListeners();
    })
    .catch(err => {
      console.error('Could not load slide timings:', err);
      // Display an error message in the slide container
      if (slidesContainer) {
          slidesContainer.innerHTML = '<div class="error-message">Could not load presentation data.</div>';
      }
    });

  // Initialize display on load
  updateMainTimeDisplay(elapsedSeconds);
});

// --- TIMER FUNCTIONALITY ---
let timerInterval = null;
let elapsedSeconds = 0;
let timerRunning = false;

// --- PER-SLIDE TIMER ---
let slideElapsedSeconds = 0;
let slideTimerInterval = null;
let lastSlideIdx = null;

function formatMmSs(secs) {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function addBreakAfterCurrentSlide() {
  // Check if a presentation is loaded
  if (!presentationsData || !presentationsData.current_presentation_id || !slideTimings || slideTimings.length === 0) {
    alert('Please open a presentation first before adding a break.');
    return;
  }

  // Create a new break entry
  const breakEntry = {
    slide: 'BREAK',
    estimated_time_seconds: 900, // 15 minutes
    actual_time_seconds: null
  };

  // Insert the break after the current slide (or at the end if no slide is selected)
  const insertIndex = (typeof currentSlideIdx === 'number' && currentSlideIdx >= 0) 
    ? currentSlideIdx + 1 
    : slideTimings.length;
  slideTimings.splice(insertIndex, 0, breakEntry);

  // Recalculate cumulative times
  let cumulativeTime = 0;
  slideTimings = slideTimings.map(slide => {
    cumulativeTime += slide.estimated_time_seconds || 0;
    return { ...slide, cumulative_time_seconds: cumulativeTime };
  });

  // Update total time display
  const totalPresentationSeconds = cumulativeTime;
  const el = document.getElementById('total-time-display');
  if (el) el.textContent = formatTime(totalPresentationSeconds);

  // Update the presentation data structure
  const dataToSave = JSON.parse(JSON.stringify(presentationsData));
  const currentPresentationId = dataToSave.current_presentation_id;
  dataToSave.presentations[currentPresentationId].slides = slideTimings.map(({ cumulative_time_seconds, ...slide }) => slide);

  // Save to backend
  fetch('/api/save_timings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(dataToSave)
  })
  .then(response => {
    if (response.ok) {
      console.log('Break added and saved successfully');
      // Update the global presentationsData
      presentationsData = dataToSave;
      // Clear any stuck editing states before refreshing UI
      clearStuckEditingStates();
      // Refresh the slides UI
      updatePresentationUI(dataToSave);
      updateTimeLeftDisplay();
      // Re-select the original slide (which is still at the same index)
      setTimeout(() => {
        updateSelectedSlideUI(currentSlideIdx + 1);
        // Scroll to show the new break that was added
        const slides = slidesContainer ? slidesContainer.querySelectorAll('.slide-progress') : [];
        if (slides[insertIndex]) {
          slides[insertIndex].scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }, 100);
    } else {
      console.error('Failed to save break to backend');
      alert('Failed to save the break. Please try again.');
    }
  })
  .catch(err => {
    console.error('Error saving break:', err);
    alert('Error saving the break. Please try again.');
  });
}

function updateSlideTimersUI() {
  // Update the elapsed time for each slide while preserving the time values
  const slides = slidesContainer ? slidesContainer.querySelectorAll('.slide-progress') : [];
  slides.forEach((slide, idx) => {
    let elapsed = '0:00';
    if (idx === currentSlideIdx) {
      elapsed = formatMmSs(slideElapsedSeconds);
    } else if (slideTimings[idx].actual_time_seconds != null) {
      elapsed = formatMmSs(slideTimings[idx].actual_time_seconds);
    }
    
    // Update only the elapsed time part, preserving the time value or input field
    const elapsedSpan = slide.querySelector('.slide-elapsed');
    const timeValue = slide.querySelector('.time-value');
    const timeInput = slide.querySelector('.time-input');
    
    if (elapsedSpan) {
      if (timeInput) {
        // Currently in edit mode - preserve input field
        elapsedSpan.innerHTML = `${elapsed} of <input type="text" class="time-input" value="${timeInput.value}" data-slide-index="${idx}">`;
        // Re-setup event listeners for the new input element
        const newTimeInput = elapsedSpan.querySelector('.time-input');
        if (newTimeInput) {
          setupTimeInputListeners(newTimeInput, idx);
        }
      } else if (timeValue) {
        // Normal mode - preserve time value span
        const plannedTime = formatMmSs(slideTimings[idx].estimated_time_seconds);
        elapsedSpan.innerHTML = `${elapsed} of <span class="time-value" data-slide-index="${idx}">${plannedTime}</span>`;
      }
    }
  });
}

function saveSlideTimingsToBackend() {
  if (!presentationsData || !presentationsData.current_presentation_id) return;
  // Prepare data for saving
  const dataToSave = JSON.parse(JSON.stringify(presentationsData));
  const currentPresentationId = dataToSave.current_presentation_id;
  // Update slides for the current presentation, removing cumulative_time_seconds
  dataToSave.presentations[currentPresentationId].slides = slideTimings.map(({ cumulative_time_seconds, ...slide }) => slide);
  fetch('/api/save_timings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(dataToSave)
  }).catch(err => console.error('Error saving timings:', err));
}

function startSlideTimer(idx) {
  if (!isPlayMode) {
    stopSlideTimer();
    return;
  }
  // Stop previous timer if running
  if (slideTimerInterval) {
    clearInterval(slideTimerInterval);
    slideTimerInterval = null;
  }
  // Save elapsed time for previous slide
  if (lastSlideIdx !== null && lastSlideIdx !== idx && slideTimings[lastSlideIdx]) {
    slideTimings[lastSlideIdx].actual_time_seconds = slideElapsedSeconds;
    saveSlideTimingsToBackend();
  }
  // Restore elapsed for new slide if it exists, otherwise 0
  slideElapsedSeconds = slideTimings[idx].actual_time_seconds || 0;
  lastSlideIdx = idx;
  updateSlideTimersUI();
  slideTimerInterval = setInterval(() => {
    slideElapsedSeconds++;
    updateSlideTimersUI();
  }, 1000);
}

function stopSlideTimer() {
  if (slideTimerInterval) {
    clearInterval(slideTimerInterval);
    slideTimerInterval = null;
  }
  // Save elapsed time for last slide
  if (lastSlideIdx !== null && slideTimings[lastSlideIdx]) {
    slideTimings[lastSlideIdx].actual_time_seconds = slideElapsedSeconds;
    saveSlideTimingsToBackend();
  }
}

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
    if (timerRunning) {
        clearInterval(timerInterval);
        timerRunning = false;
        playPauseIcon.src = 'static/images/008-play-button.png';
        playPauseIcon.alt = 'Play';
        isPlayMode = false;
        stopSlideTimer();
    }
}

function navigateToNextSlide() {
  if (!slideTimings || slideTimings.length === 0) return;
  
  const nextIndex = currentSlideIdx + 1;
  if (nextIndex >= slideTimings.length) return; // Already at last slide
  
  const nextSlide = slideTimings[nextIndex];
  
  if (nextSlide.slide === 'BREAK') {
    // Next item is a break - just update UI selection
    updateSelectedSlideByIndex(nextIndex);
  } else {
    // Next item is a regular slide - calculate Keynote slide number and call API
    const keynoteSlideNumber = calculateKeynoteSlideNumber(nextIndex);
    if (keynoteSlideNumber > 0) {
      fetch(`/api/goto_slide/${keynoteSlideNumber}`, { method: 'POST' })
        .then(response => {
          if (!response.ok) {
            response.json().then(data => console.error('Failed to move to next slide:', data.message));
          }
          // UI will be updated by the websocket event for regular slides
        })
        .catch(error => console.error('Error calling goto_slide API:', error));
    }
  }
}

function navigateToPreviousSlide() {
  if (!slideTimings || slideTimings.length === 0) return;
  
  const prevIndex = currentSlideIdx - 1;
  if (prevIndex < 0) return; // Already at first slide
  
  const prevSlide = slideTimings[prevIndex];
  
  if (prevSlide.slide === 'BREAK') {
    // Previous item is a break - just update UI selection
    updateSelectedSlideByIndex(prevIndex);
  } else {
    // Previous item is a regular slide - calculate Keynote slide number and call API
    const keynoteSlideNumber = calculateKeynoteSlideNumber(prevIndex);
    if (keynoteSlideNumber > 0) {
      fetch(`/api/goto_slide/${keynoteSlideNumber}`, { method: 'POST' })
        .then(response => {
          if (!response.ok) {
            response.json().then(data => console.error('Failed to move to previous slide:', data.message));
          }
          // UI will be updated by the websocket event for regular slides
        })
        .catch(error => console.error('Error calling goto_slide API:', error));
    }
  }
}

function calculateKeynoteSlideNumber(slideIndex) {
  // Calculate the actual Keynote slide number by counting non-break slides up to this index
  let keynoteSlideNumber = 0;
  for (let i = 0; i <= slideIndex && i < slideTimings.length; i++) {
    if (slideTimings[i].slide !== 'BREAK') {
      keynoteSlideNumber++;
    }
  }
  return keynoteSlideNumber;
}

// --- Patch slide click listeners ---
function addSlideClickListeners() {
  const slides = slidesContainer ? slidesContainer.querySelectorAll('.slide-progress') : [];
  slides.forEach((slide, idx) => {
    slide.onclick = () => selectSlide(idx);
  });
}

function clearStuckEditingStates() {
  // Clear any stuck editing states that might cause freezing
  editingSlideIndex = -1;
  
  // Find any lingering time-input elements and reset their flags
  const stuckInputs = document.querySelectorAll('.time-input');
  stuckInputs.forEach(input => {
    if (input.dataset) {
      input.dataset.isFinishing = 'false';
    }
  });
  
  // Make sure all edit icons are visible
  const editIcons = document.querySelectorAll('.edit-icon');
  editIcons.forEach(icon => {
    icon.style.display = 'flex';
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

// Function to start editing a time value (triggered by edit icon)
function startEditingTime(slideIndex) {
  const slideElement = document.getElementById(`slide-${slideTimings[slideIndex].slide}`);
  if (!slideElement) return;
  
  const timeValue = slideElement.querySelector('.time-value');
  const editIcon = slideElement.querySelector('.edit-icon');
  
  if (!timeValue || !editIcon) return;
  
  // Store the current value for potential rollback
  const currentValue = timeValue.textContent;
  
  // Replace the time value span with an input field
  const timeInput = document.createElement('input');
  timeInput.type = 'text';
  timeInput.className = 'time-input';
  timeInput.value = currentValue;
  timeInput.setAttribute('data-slide-index', slideIndex);
  
  // Replace the span with the input
  timeValue.parentNode.replaceChild(timeInput, timeValue);
  
  // Hide the edit icon during editing
  editIcon.style.display = 'none';
  
  // Set up event listeners for the input field
  setupTimeInputListeners(timeInput, slideIndex, currentValue);
  
  // Focus and select the text
  timeInput.focus();
  timeInput.select();
  
  editingSlideIndex = slideIndex;
}

// Function to set up event listeners for time input fields
function setupTimeInputListeners(timeInput, slideIndex, originalValue) {
  // Prevent slide click when clicking on input
  timeInput.addEventListener('click', (e) => {
    e.stopPropagation();
  });

  // Handle Enter key - save and exit edit mode
  timeInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      finishEditingTime(timeInput, slideIndex, true);
    }
    
    // Handle Escape key - cancel and revert changes
    if (e.key === 'Escape') {
      e.preventDefault();
      finishEditingTime(timeInput, slideIndex, false, originalValue);
    }
  });

  // Handle blur - save changes when losing focus
  timeInput.addEventListener('blur', (e) => {
    // Add a small delay to allow other handlers (like Enter keydown) to complete first
    setTimeout(() => {
      // Only proceed if the input is still in the DOM and not already finishing
      if (timeInput && timeInput.parentNode && timeInput.dataset.isFinishing !== 'true') {
        finishEditingTime(timeInput, slideIndex, true);
      }
    }, 0);
  });

  // Allow only valid time characters
  timeInput.addEventListener('input', (e) => {
    // Remove any non-numeric characters except colon
    let value = e.target.value.replace(/[^0-9:]/g, '');
    
    // Ensure proper format (M:SS or MM:SS)
    if (value.length > 5) {
      value = value.substring(0, 5);
    }
    
    e.target.value = value;
  });
}

// Function to finish editing and convert back to label
function finishEditingTime(timeInput, slideIndex, shouldSave, fallbackValue = null) {
  // Prevent multiple calls to finishEditingTime for the same editing session
  if (!timeInput || !timeInput.parentNode || timeInput.dataset.isFinishing === 'true') {
    return;
  }
  
  // Mark as finishing to prevent race conditions
  timeInput.dataset.isFinishing = 'true';
  
  // Clear the flag after a timeout to prevent permanent freezing
  setTimeout(() => {
    if (timeInput && timeInput.dataset) {
      timeInput.dataset.isFinishing = 'false';
    }
  }, 100);
  
  const slideElement = document.getElementById(`slide-${slideTimings[slideIndex].slide}`);
  if (!slideElement) return;
  
  const editIcon = slideElement.querySelector('.edit-icon');
  let finalValue = fallbackValue;
  
  if (shouldSave && !fallbackValue) {
    const timeValue = timeInput.value.trim();
    const newTotalSeconds = parseTimeInput(timeValue);

    if (newTotalSeconds !== null && !isNaN(newTotalSeconds)) {
      // Valid input - save the changes
      slideTimings[slideIndex].estimated_time_seconds = newTotalSeconds;

      // Recalculate cumulative times
      let cumulativeTime = 0;
      slideTimings = slideTimings.map(slide => {
          cumulativeTime += slide.estimated_time_seconds || 0;
          return { ...slide, cumulative_time_seconds: cumulativeTime };
      });

      // Update total time display
      const totalPresentationSeconds = cumulativeTime;
      const el = document.getElementById('total-time-display');
      if (el) el.textContent = formatTime(totalPresentationSeconds);
      
      finalValue = formatMmSs(newTotalSeconds);

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

      // Add visual feedback
      slideElement.classList.add('timing-updated');
      setTimeout(() => {
        slideElement.classList.remove('timing-updated');
      }, 1000);
      updateTimeLeftDisplay();
    } else {
      // Invalid input - revert to original value
      finalValue = formatMmSs(slideTimings[slideIndex].estimated_time_seconds);
    }
  }
  
  // Create new time value span
  const timeValue = document.createElement('span');
  timeValue.className = 'time-value';
  timeValue.setAttribute('data-slide-index', slideIndex);
  timeValue.textContent = finalValue;
  
  // Replace the input with the span - with additional safety check
  let replacementSuccessful = false;
  try {
    if (timeInput.parentNode && timeInput.parentNode.contains(timeInput)) {
      timeInput.parentNode.replaceChild(timeValue, timeInput);
      replacementSuccessful = true;
    }
  } catch (error) {
    console.error('Error replacing time input element:', error);
    // Fallback: try to find and replace by selector
    const parentContainer = slideElement.querySelector('.slide-elapsed');
    if (parentContainer) {
      const existingInput = parentContainer.querySelector('.time-input');
      if (existingInput) {
        try {
          existingInput.parentNode.replaceChild(timeValue, existingInput);
          replacementSuccessful = true;
        } catch (fallbackError) {
          console.error('Fallback replacement also failed:', fallbackError);
        }
      }
    }
  }
  
  // Show the edit icon again
  if (editIcon) {
    editIcon.style.display = 'flex';
  }
  
  // Always reset editing state, even if replacement failed
  editingSlideIndex = -1;
  
  // Clear the finishing flag on the input element if it still exists
  if (timeInput && timeInput.dataset) {
    timeInput.dataset.isFinishing = 'false';
  }
}

// Function to parse time input (supports formats like "1:30", "90", "2:00")
function parseTimeInput(timeStr) {
  if (!timeStr) return null;
  
  // If it contains a colon, parse as MM:SS
  if (timeStr.includes(':')) {
    const parts = timeStr.split(':');
    if (parts.length === 2) {
      const minutes = parseInt(parts[0], 10);
      const seconds = parseInt(parts[1], 10);
      
      if (!isNaN(minutes) && !isNaN(seconds) && seconds < 60) {
        return minutes * 60 + seconds;
      }
    }
  } else {
    // If no colon, treat as total seconds
    const totalSeconds = parseInt(timeStr, 10);
    if (!isNaN(totalSeconds) && totalSeconds >= 0) {
      return totalSeconds;
    }
  }
  
  return null;
}

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

// Function to reset all slide elapsed times when opening a new presentation
function resetSlideElapsedTimes(timingsData) {
  if (!timingsData || !timingsData.presentations || !timingsData.current_presentation_id) {
    console.log('No valid presentation data to reset timings for');
    return;
  }
  
  const currentPresentationId = timingsData.current_presentation_id;
  const currentPresentation = timingsData.presentations[currentPresentationId];
  
  if (!currentPresentation || !currentPresentation.slides) {
    console.log('No slides found in current presentation');
    return;
  }
  
  console.log('Resetting elapsed times for all slides in presentation:', currentPresentationId);
  
  // Reset actual_time_seconds to null for all slides
  currentPresentation.slides.forEach(slide => {
    slide.actual_time_seconds = null;
  });
  
  // Reset current slide timing state
  slideElapsedSeconds = 0;
  lastSlideIdx = null;
  
  // Stop any running slide timer
  if (slideTimerInterval) {
    clearInterval(slideTimerInterval);
    slideTimerInterval = null;
  }
  
  // Update the global presentationsData
  presentationsData = timingsData;
  
  // Save the reset data to the backend
  fetch('/api/save_timings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(timingsData)
  })
  .then(response => {
    if (response.ok) {
      console.log('Successfully reset slide elapsed times');
    } else {
      console.error('Failed to save reset slide timings');
    }
  })
  .catch(err => {
    console.error('Error saving reset slide timings:', err);
  });
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
              // Reset elapsed times for all slides when opening a new presentation
              resetSlideElapsedTimes(timingsData);
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
            .then(timingsData => {
              // Reset elapsed times for all slides when opening a new presentation
              resetSlideElapsedTimes(timingsData);
              updatePresentationUI(timingsData);
            })
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

function deleteBreakSlide(slideIndex) {
  // Check if a presentation is loaded
  if (!presentationsData || !presentationsData.current_presentation_id || !slideTimings || slideTimings.length === 0) {
    console.log('No valid presentation data to delete slide from');
    return;
  }
  
  // Check if the slide to be deleted is a break
  if (slideTimings[slideIndex].slide !== 'BREAK') {
    console.log('Selected slide is not a break');
    return;
  }
  
  console.log('Deleting slide:', slideTimings[slideIndex]);
  
  // Remove the break from the slide timings
  slideTimings.splice(slideIndex, 1);
  
  // Recalculate cumulative times
  let cumulativeTime = 0;
  slideTimings = slideTimings.map(slide => {
    cumulativeTime += slide.estimated_time_seconds || 0;
    return { ...slide, cumulative_time_seconds: cumulativeTime };
  });
  
  // Update total time display
  const totalPresentationSeconds = cumulativeTime;
  const el = document.getElementById('total-time-display');
  if (el) el.textContent = formatTime(totalPresentationSeconds);
  
  // Update the presentation data structure
  const dataToSave = JSON.parse(JSON.stringify(presentationsData));
  const currentPresentationId = dataToSave.current_presentation_id;
  dataToSave.presentations[currentPresentationId].slides = slideTimings.map(({ cumulative_time_seconds, ...slide }) => slide);
  
  // Save to backend
  fetch('/api/save_timings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(dataToSave)
  })
  .then(response => {
    if (response.ok) {
      console.log('Slide deleted and saved successfully');
      // Update the global presentationsData
      presentationsData = dataToSave;
      // Clear any stuck editing states before refreshing UI
      clearStuckEditingStates();
      // Refresh the slides UI
      updatePresentationUI(dataToSave);
      updateTimeLeftDisplay();
    } else {
      console.error('Failed to delete slide from backend');
      alert('Failed to delete the slide. Please try again.');
    }
  })
  .catch(err => {
    console.error('Error deleting slide:', err);
    alert('Error deleting the slide. Please try again.');
  });
}

function updateTimeLeftDisplay() {
  const timeLeftEl = document.getElementById('time-left-display');
  if (!timeLeftEl || !slideTimings || slideTimings.length === 0 || currentSlideIdx < 0 || currentSlideIdx >= slideTimings.length) {
    if (timeLeftEl) timeLeftEl.textContent = '-';
    return;
  }
  let totalLeft = 0;
  for (let i = currentSlideIdx + 1; i < slideTimings.length; i++) {
    totalLeft += slideTimings[i].estimated_time_seconds || 0;
  }
  timeLeftEl.textContent = formatTime(totalLeft);
}

// --- EDIT TIME OVERLAY ---
function openEditTimeOverlay() {
    // Populate with current elapsed time
    const h = Math.floor(elapsedSeconds / 3600);
    const m = Math.floor((elapsedSeconds % 3600) / 60);
    const s = elapsedSeconds % 60;

    editHoursInput.value = h;
    editMinutesInput.value = m;
    editSecondsInput.value = s;

    if (editTimeOverlay) editTimeOverlay.style.display = 'flex';
}

function closeEditTimeOverlay() {
    if (editTimeOverlay) editTimeOverlay.style.display = 'none';
}

function saveEditedTime() {
    const hours = parseInt(editHoursInput.value, 10) || 0;
    const minutes = parseInt(editMinutesInput.value, 10) || 0;
    const seconds = parseInt(editSecondsInput.value, 10) || 0;

    const totalSeconds = (hours * 3600) + (minutes * 60) + seconds;

    elapsedSeconds = totalSeconds;
    updateMainTimeDisplay(elapsedSeconds);
    saveElapsedTimeToBackend(elapsedSeconds);

    closeEditTimeOverlay();
} 