# Keynote Remote - TODO & Improvement Roadmap

## IMMEDIATE TODOs
[X] Fix the slide time edit function - the + and - buttons make it too slow - just go back to typeing in a number



## 🚀 Presentation Enhancement Features

### 1. Smart Timing Recommendations
- [ ] **AI-Powered Timing Suggestions**: Analyze slide content and suggest optimal timing
  - [ ] Text density analysis for timing estimates
  - [ ] Image/media content consideration
  - [ ] Slide complexity scoring
- [ ] **Presentation Breaks**: Add a Break slide in between 2 existing slides
  - [X] Add a Break "slide" that is not an actual slide 
  - [X] For presentations that don't have breaks - helps plan timing
  - [X] Allow users to delete a "Break"
- [ ] Use AI to estimate the timing for slides
  - [ ] Create an agent(s) to extract slide content and send it to LLM for estimation
  - [ ] Agent can determine # of slides, extract each slide's content, and batch slides for LLM analysis


## 🎯 User Experience Improvements

### 2. Mobile-Optimized Interface
- [ ] **Dedicated Mobile App**: React Native or PWA for better mobile experience
  - [ ] Native iOS app development
  - [ ] Android compatibility
  - [ ] App Store deployment
- [ ] **Gesture Controls**: Swipe navigation for slides
  - [ ] Left/right swipe for navigation
  - [ ] Pinch to zoom on timing displays
  - [ ] Pull-to-refresh functionality



### 5. Visual Enhancements
- [ ] **Slide Thumbnails**: Preview current/next slides in the interface
  - [ ] Keynote slide preview API integration
  - [ ] Thumbnail caching system
  - [ ] Preview quality settings
- [ ] **Progress Visualization**: Better visual progress indicators with slide previews
  - [ ] Timeline view with slide thumbnails
  - [ ] Interactive progress bar with slide markers
  - [ ] Remaining time visualization
- [ ] **Dark/Light Theme Toggle**: Automatic based on system preferences
  - [ ] System theme detection
  - [ ] Manual theme override
  - [ ] Custom color schemes
- [ ] **Customizable Dashboard**: Drag-and-drop interface customization
  - [ ] Widget-based layout system
  - [ ] Persistent layout preferences
  - [ ] Multiple dashboard profiles


### 3. Advanced Timing Features
- [ ] **Section-Based Timing**: Group slides into sections with section timing goals
  - [ ] Section definition interface
  - [ ] Section timing targets
  - [ ] Section progress tracking
- [ ] **Conditional Timing**: Different timing based on audience interaction
  - [ ] Q&A time buffers
  - [ ] Interactive slide timing
  - [ ] Audience engagement detection
- [ ] **Practice Mode**: Rehearsal mode with feedback and improvement suggestions
  - [ ] Practice session recording
  - [ ] Performance comparison
  - [ ] Improvement recommendations

### 3. Integration Capabilities
- [ ] **Zoom/Teams Integration**: Display timing info during virtual presentations
  - [ ] Virtual background with timing info
  - [ ] Chat bot for timing updates
  - [ ] Meeting integration APIs
- [ ] **Clock/timer**: Display a clock or timer for breaks and share via Zoom
  - [ ] Countdown timer for breaks
  - [ ] Auto-share as a Zoom screen
- [ ] **Auto polls**: Run polls based on slide content
  - [ ] For sldies that have mutliple-choice questions, run a poll based on them
  - [ ] Would use AI to do this work


## 📊 Advanced Monitoring & Control


### 11. Smart Alerts & Notifications
- [ ] **Intelligent Warnings**: Context-aware timing alerts
  - [ ] Machine learning for personalized alerts
  - [ ] Adaptive warning thresholds
  - [ ] Predictive timing alerts
- [ ] **Custom Alert Sounds**: Different sounds for different timing states
  - [ ] Sound library management
  - [ ] Custom sound upload
  - [ ] Volume and timing controls
- [ ] **Visual Cues**: Screen border colors, popup notifications
  - [ ] Customizable visual alerts
  - [ ] Non-intrusive notification system
  - [ ] Alert priority levels


### 12. Presentation Recording & Playback
- [ ] **Timing Recordings**: Record actual timing data for later analysis
  - [ ] Session recording system
  - [ ] Timing data export
  - [ ] Performance replay functionality
- [ ] **Rehearsal Playback**: Play back previous presentations for training
  - [ ] Rehearsal session management
  - [ ] Training mode interface
  - [ ] Progress tracking for improvement
- [ ] **Save Slide Timing**: Save the elapsed time values when a presentation is done
  - [ ] When user hits "Close Presentation" save the elapsed and target time values to a file for latert reference
  


### 13. Content Sections
- [ ] **Content Sections**: Categorize slides by section
  - [ ] Add a new label in between slides that will act as a section maker
  - [ ] Any slides below that section marker will be indented
  - [ ] A section will have a timing summary of all slides within it


## 14. Slide priority and time adjustments
- [ ] Allow each slide to have a priority setting
- [ ] If running behind - an AI could adjust remaining slide times to catch up based on priority
- [ ] Sections (see above) can have their own priority settings


### 15. Testing
- [ ] Create test plans and tools


### 16. Presentation Notes
- [ ] Need a way to display presentation notes






## 📝 Implementation Notes


### Technical Considerations
- Maintain backward compatibility with existing timing files
- Ensure WebSocket performance with new features
- Consider API rate limiting for new endpoints
- Plan for database migration if persistence is added
- Design for horizontal scaling if enterprise features are added

### Testing Strategy
- Unit tests for all new features
- Integration tests for WebSocket functionality
- Cross-browser testing for web interface improvements
- Mobile device testing for responsive features
- Performance testing for real-time features
