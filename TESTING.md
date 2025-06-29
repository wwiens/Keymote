# Keymote Testing Guide

This document outlines the testing strategy for the Keymote application, the tools used, and how to run the test suite. A robust, multi-layered testing approach ensures the application is reliable, secure, and maintainable.

## Testing Strategy

The testing strategy is divided into three layers:

1.  **Backend Unit & Integration Tests**: These form the foundation of our testing pyramid. They are fast, reliable, and test the core application logic in isolation from the live Keynote application and the host file system. All interactions with external dependencies (like AppleScript and file I/O) are mocked.
2.  **Frontend Unit Tests**: These tests focus on the client-side JavaScript code. They verify UI logic, WebSocket event handling, and DOM manipulation without needing a full browser environment.
3.  **End-to-End (E2E) Tests**: These are the highest-level tests. They simulate real user interactions in a browser, ensuring all parts of the application (frontend, backend, and the WebSocket channel) work together seamlessly.

## 1. Backend Testing

The backend tests cover the Flask server, API endpoints, and WebSocket event handling.

### Tools

-   **`pytest`**: The core test runner for executing the test suite.
-   **`pytest-mock`**: Used extensively to create "mocks," which are simulated versions of external dependencies like `subprocess` and file system functions. This allows us to test the application's logic without actually running Keynote or modifying real files.
-   **`python-socketio[client]`**: Provides a test client to simulate WebSocket connections and test real-time event emissions.

### How to Run Backend Tests

1.  **Install Dependencies**: Make sure you have installed all the required packages, including the testing tools:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Run the Test Suite**: Execute the following command from the project's root directory:
    ```bash
    pytest -v
    ```
    The `-v` flag provides verbose output, showing each test that is run.

### Test Structure

-   **`tests/`**: All test files are located in this directory.
-   **`tests/conftest.py`**: This file contains shared fixtures, such as the Flask test client, which are automatically available to all tests.
-   **`tests/test_server.py`**: This file contains the tests for the `server.py` application.
-   **`pytest.ini`**: This configuration file ensures that `pytest` can correctly locate the application modules.

## 2. Frontend Testing (Recommended)

Frontend tests will validate the client-side logic that runs in the browser.

### Recommended Tools

-   **`Jest`**: A popular JavaScript testing framework that is well-suited for testing UI components and logic.
-   **`jsdom`**: Simulates a browser's DOM environment, allowing tests to run in Node.js without needing a real browser.

### What to Test

-   **WebSocket Event Handlers**: Ensure the UI correctly updates when it receives messages from the server (e.g., `slide_update`).
-   **DOM Manipulation**: Verify that buttons, timers, and slide counters are updated correctly based on user actions and server events.
-   **API Calls**: Mock the `fetch` API to test how the frontend handles responses from the server.

## 3. End-to-End (E2E) Testing (Recommended)

E2E tests provide the highest level of confidence by simulating a complete user journey.

### Recommended Tools

-   **`Playwright`** or **`Cypress`**: Modern E2E testing frameworks that allow you to write scripts that control a real browser.

### What to Test

-   **User Flows**: Test the entire process of opening a presentation, starting it, navigating through slides, and seeing the timer update.
-   **Backend Integration**: For the most comprehensive testing, these tests can be run against a live server with a mocked Keynote instance. For faster, more stable UI tests, the backend API responses can be mocked. 