/**
 * Clip Suggestion Extension - Popup Script
 * Handles video ID extraction, API calls, and UI rendering
 */

// Configuration
const CONFIG = {
    // Deployed API URL on Render
    API_URL: 'https://clip-suggestion-extension.onrender.com/api/clip-ideas',
    CLIENT_HEADER: 'indiedoers-extension'
};

// DOM Elements
const elements = {
    generateBtn: null,
    btnText: null,
    btnLoader: null,
    videoInfo: null,
    videoIdDisplay: null,
    errorContainer: null,
    errorMessage: null,
    retryBtn: null,
    resultsContainer: null,
    resultsCount: null,
    ideasList: null,
    emptyState: null,
    remainingRequests: null
};

// State
let currentVideoId = null;

/**
 * Initialize the popup
 */
async function init() {
    // Cache DOM elements
    elements.generateBtn = document.getElementById('generate-btn');
    elements.btnText = document.querySelector('.btn-text');
    elements.btnLoader = document.querySelector('.btn-loader');
    elements.videoInfo = document.getElementById('video-info');
    elements.videoIdDisplay = document.getElementById('video-id-display');
    elements.errorContainer = document.getElementById('error-container');
    elements.errorMessage = document.getElementById('error-message');
    elements.retryBtn = document.getElementById('retry-btn');
    elements.resultsContainer = document.getElementById('results-container');
    elements.resultsCount = document.getElementById('results-count');
    elements.ideasList = document.getElementById('ideas-list');
    elements.emptyState = document.getElementById('empty-state');
    elements.remainingRequests = document.getElementById('remaining-requests');

    // Add event listeners
    elements.generateBtn.addEventListener('click', handleGenerate);
    elements.retryBtn.addEventListener('click', handleGenerate);

    // Check current tab
    await checkCurrentTab();
}

/**
 * Check if current tab is a YouTube video page
 */
async function checkCurrentTab() {
    try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

        if (!tab?.url) {
            showEmptyState('Unable to access current tab');
            return;
        }

        const videoId = extractVideoId(tab.url);

        if (videoId) {
            currentVideoId = videoId;
            showVideoInfo(videoId);
            elements.generateBtn.disabled = false;
        } else {
            showEmptyState('Open a YouTube video to generate clip ideas');
            elements.generateBtn.disabled = true;
        }
    } catch (error) {
        console.error('Error checking tab:', error);
        showEmptyState('Unable to access YouTube tab');
        elements.generateBtn.disabled = true;
    }
}

/**
 * Extract video ID from YouTube URL
 */
function extractVideoId(url) {
    try {
        const urlObj = new URL(url);

        // Standard watch URL
        if (urlObj.hostname.includes('youtube.com') && urlObj.pathname === '/watch') {
            return urlObj.searchParams.get('v');
        }

        // Shortened URL
        if (urlObj.hostname === 'youtu.be') {
            return urlObj.pathname.slice(1);
        }

        // Embed URL
        if (urlObj.pathname.startsWith('/embed/')) {
            return urlObj.pathname.split('/embed/')[1];
        }

        return null;
    } catch {
        return null;
    }
}

/**
 * Handle generate button click
 */
async function handleGenerate() {
    if (!currentVideoId) {
        showError('No video ID found. Please open a YouTube video.');
        return;
    }

    setLoading(true);
    hideError();
    hideResults();

    try {
        const response = await fetch(CONFIG.API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Client': CONFIG.CLIENT_HEADER
            },
            body: JSON.stringify({
                videoId: currentVideoId,
                videoUrl: `https://www.youtube.com/watch?v=${currentVideoId}`,
                mode: 'shorts'
            })
        });

        const data = await response.json();

        if (!response.ok) {
            // Handle error response
            const error = data.detail || data;
            handleApiError(error);
            return;
        }

        // Success - render ideas
        renderIdeas(data.ideas);

    } catch (error) {
        console.error('API error:', error);
        showError('Failed to connect to the server. Please try again.');
    } finally {
        setLoading(false);
    }
}

/**
 * Handle API error responses
 */
function handleApiError(error) {
    const errorCode = error.error || 'UNKNOWN';
    const message = error.message || 'An unexpected error occurred.';

    switch (errorCode) {
        case 'TRANSCRIPT_NOT_AVAILABLE':
            showError("This video doesn't have an accessible transcript. Try another video with captions enabled.");
            break;
        case 'RATE_LIMITED':
            showError('Daily limit reached. Try again tomorrow!');
            break;
        case 'INVALID_INPUT':
            showError('Invalid video. Please try a different YouTube video.');
            break;
        case 'OPENAI_ERROR':
            showError('AI service temporarily unavailable. Please try again.');
            break;
        default:
            showError(message);
    }
}

/**
 * Render clip ideas
 */
function renderIdeas(ideas) {
    elements.ideasList.innerHTML = '';
    elements.resultsCount.textContent = `${ideas.length} ideas`;

    ideas.forEach((idea, index) => {
        const card = createIdeaCard(idea, index + 1);
        elements.ideasList.appendChild(card);
    });

    showResults();
}

/**
 * Create an idea card element
 */
function createIdeaCard(idea, number) {
    const duration = idea.end_seconds - idea.start_seconds;

    const card = document.createElement('div');
    card.className = 'idea-card';
    card.style.opacity = '0';

    card.innerHTML = `
    <div class="idea-header">
      <span class="idea-number">${number}</span>
      <div class="idea-timestamps">
        <span class="timestamp">${idea.start}</span>
        <span class="timestamp-arrow">→</span>
        <span class="timestamp">${idea.end}</span>
        <span class="idea-duration">${duration}s</span>
      </div>
    </div>
    <div class="idea-body">
      <div class="idea-hook">${escapeHtml(idea.hook)}</div>
      <div class="idea-why">${escapeHtml(idea.why)}</div>
      ${idea.suggested_caption ? `
        <div class="idea-caption">💬 ${escapeHtml(idea.suggested_caption)}</div>
      ` : ''}
    </div>
    <div class="idea-footer">
      <button class="copy-btn" data-idea='${JSON.stringify(idea).replace(/'/g, "\\'")}'>
        <span class="copy-icon">📋</span>
        <span class="copy-text">Copy</span>
      </button>
    </div>
  `;

    // Add copy button event listener
    const copyBtn = card.querySelector('.copy-btn');
    copyBtn.addEventListener('click', () => handleCopy(copyBtn, idea));

    return card;
}

/**
 * Handle copy button click
 */
async function handleCopy(button, idea) {
    const formattedText = formatIdeaForCopy(idea);

    try {
        await navigator.clipboard.writeText(formattedText);

        // Show success state
        const copyText = button.querySelector('.copy-text');
        const copyIcon = button.querySelector('.copy-icon');
        const originalText = copyText.textContent;
        const originalIcon = copyIcon.textContent;

        button.classList.add('copied');
        copyText.textContent = 'Copied!';
        copyIcon.textContent = '✓';

        setTimeout(() => {
            button.classList.remove('copied');
            copyText.textContent = originalText;
            copyIcon.textContent = originalIcon;
        }, 2000);
    } catch (error) {
        console.error('Copy failed:', error);
    }
}

/**
 * Format idea for clipboard
 */
function formatIdeaForCopy(idea) {
    const duration = idea.end_seconds - idea.start_seconds;
    let text = `${idea.start}–${idea.end} (${duration}s)\n`;
    text += `Hook: ${idea.hook}\n`;
    text += `Why: ${idea.why}`;
    if (idea.suggested_caption) {
        text += `\nCaption: ${idea.suggested_caption}`;
    }
    return text;
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// UI State Management

function setLoading(isLoading) {
    elements.generateBtn.disabled = isLoading;
    elements.btnText.classList.toggle('hidden', isLoading);
    elements.btnLoader.classList.toggle('hidden', !isLoading);
}

function showVideoInfo(videoId) {
    elements.videoIdDisplay.textContent = videoId;
    elements.videoInfo.classList.remove('hidden');
    elements.emptyState.classList.add('hidden');
}

function showEmptyState(message) {
    elements.emptyState.querySelector('p').textContent = message;
    elements.emptyState.classList.remove('hidden');
    elements.videoInfo.classList.add('hidden');
}

function showError(message) {
    elements.errorMessage.textContent = message;
    elements.errorContainer.classList.remove('hidden');
    elements.emptyState.classList.add('hidden');
}

function hideError() {
    elements.errorContainer.classList.add('hidden');
}

function showResults() {
    elements.resultsContainer.classList.remove('hidden');
    elements.emptyState.classList.add('hidden');
}

function hideResults() {
    elements.resultsContainer.classList.add('hidden');
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', init);
