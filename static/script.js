const API_BASE = '';

// DOM Elements
const voiceGrid = document.getElementById('voice-grid');
const fileInput = document.getElementById('file-input');
const dropZone = document.getElementById('drop-zone');
const fileInfo = document.getElementById('file-info');
const convertBtn = document.getElementById('convert-btn');
const progressArea = document.getElementById('progress-area');
const progressBar = document.getElementById('progress-bar');
const statusText = document.getElementById('status-text');
const resultArea = document.getElementById('result-area');
const audioPlayer = document.getElementById('audio-player');
const downloadLink = document.getElementById('download-link');
const selectedVoiceInput = document.getElementById('selected-voice-id');
const toast = document.getElementById('toast');

// Icons map for categories
const ICONS = {
    'American Male': 'fa-person',
    'American Female': 'fa-person-dress',
    'British Male': 'fa-person',
    'British Female': 'fa-person-dress',
    'Australian Male': 'fa-person',
    'Australian Female': 'fa-person-dress'
};

// --- Initialization ---
async function init() {
    try {
        const res = await fetch(`${API_BASE}/voices`);
        const voices = await res.json();
        renderVoices(voices);
    } catch (e) {
        showToast('Failed to load voices. Ensure backend is running.', 'error');
    }
}

function renderVoices(voices) {
    voiceGrid.innerHTML = '';
    voices.forEach((voice, index) => {
        const iconClass = ICONS[voice.category] || 'fa-microphone';
        const isSelected = index === 0; // Default select first

        const card = document.createElement('div');
        card.className = `p-4 rounded-xl border border-white/10 cursor-pointer transition-all hover:bg-white/5 voice-card ${isSelected ? 'ring-2 ring-primary bg-primary/10' : 'bg-white/5'}`;
        card.dataset.id = voice.id;

        card.innerHTML = `
            <div class="flex items-center space-x-4">
                <div class="w-10 h-10 rounded-full bg-gradient-to-br from-indigo-500 to-purple-500 flex items-center justify-center">
                    <i class="fas ${iconClass} text-white text-sm"></i>
                </div>
                <div>
                    <h3 class="font-bold text-sm text-gray-200">${voice.category}</h3>
                </div>
            </div>
        `;

        card.addEventListener('click', () => selectVoice(card, voice.id));
        voiceGrid.appendChild(card);
    });
}

function selectVoice(card, id) {
    // Deselect all
    document.querySelectorAll('.voice-card').forEach(c => {
        c.classList.remove('ring-2', 'ring-primary', 'bg-primary/10');
        c.classList.add('bg-white/5');
    });
    // Select this
    card.classList.remove('bg-white/5');
    card.classList.add('ring-2', 'ring-primary', 'bg-primary/10');
    selectedVoiceInput.value = id;
}

// --- Upload Handling ---
dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('border-primary', 'bg-primary/5');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('border-primary', 'bg-primary/5');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('border-primary', 'bg-primary/5');
    if (e.dataTransfer.files.length) {
        handleFile(e.dataTransfer.files[0]);
    }
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) handleFile(e.target.files[0]);
});

function handleFile(file) {
    if (file.type !== 'application/pdf') {
        showToast('Please upload a PDF file.', 'error');
        return;
    }
    fileInfo.textContent = `Selected: ${file.name}`;
    fileInfo.classList.remove('hidden');
}

// --- Conversion ---
convertBtn.addEventListener('click', async () => {
    const file = fileInput.files[0];
    const voiceId = selectedVoiceInput.value;

    if (!file) {
        showToast('Please upload a PDF first.', 'error');
        return;
    }

    // UI State: Processing
    convertBtn.classList.add('opacity-50', 'pointer-events-none');
    convertBtn.textContent = 'Processing...';
    progressArea.classList.remove('hidden');
    resultArea.classList.add('hidden');
    progressBar.style.width = '30%';
    statusText.textContent = 'Extracting text and uploading...';

    const formData = new FormData();
    formData.append('file', file);
    formData.append('voice_id', voiceId);

    try {
        progressBar.style.width = '60%';
        statusText.textContent = 'Generating Audio with Murf AI... (This may take a moment)';

        const response = await fetch(`${API_BASE}/convert`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Conversion failed');
        }

        const data = await response.json();

        progressBar.style.width = '100%';
        statusText.textContent = 'Done!';

        // Success
        setTimeout(() => {
            progressArea.classList.add('hidden');
            showResult(data.playback_url || data.download_url, data.download_url);
            showToast('Conversion Successful!', 'success');
            convertBtn.textContent = 'Convert Another';
            convertBtn.classList.remove('opacity-50', 'pointer-events-none');
        }, 800);

    } catch (e) {
        progressArea.classList.add('hidden');
        convertBtn.classList.remove('opacity-50', 'pointer-events-none');
        convertBtn.textContent = 'Convert to Audiobook';
        showToast(e.message, 'error');
    }
});

function showResult(playbackUrl, downloadUrl) {
    resultArea.classList.remove('hidden');
    audioPlayer.src = playbackUrl;
    downloadLink.href = downloadUrl;
}

// --- Toast ---
function showToast(msg, type = 'default') {
    toast.textContent = msg;
    toast.className = `fixed bottom-5 right-5 px-6 py-4 rounded-xl shadow-2xl transition-all z-50 font-medium translate-y-0 opacity-100 ${type === 'error' ? 'bg-red-500 text-white' : 'bg-white text-dark'}`;

    setTimeout(() => {
        toast.classList.add('translate-y-20', 'opacity-0');
    }, 3000);
}

// Start
init();
