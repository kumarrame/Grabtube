var API_BASE = '/api';

var urlInput    = document.getElementById('urlInput');
var pasteBtn    = document.getElementById('pasteBtn');
var formatChips = document.querySelectorAll('.format-chip');
var qualityGrid = document.getElementById('qualityGrid');
var qualitySec  = document.getElementById('qualitySection');
var downloadBtn = document.getElementById('downloadBtn');
var errorMsg    = document.getElementById('errorMsg');
var errorText   = document.getElementById('errorText');
var loadingEl   = document.getElementById('loadingOverlay');
var loadingText = document.getElementById('loadingText');
var resultCard  = document.getElementById('resultCard');

var selectedFormat  = 'mp4';
var selectedQuality = '720p HD';

var qualities = {
  mp4: [
    { label: '360p',      size: '~30 MB' },
    { label: '720p HD',   size: '~80 MB' },
    { label: '1080p FHD', size: '~150 MB' }
  ],
  mp3: [
    { label: '128 kbps', size: '~4 MB' },
    { label: '192 kbps', size: '~6 MB' },
    { label: '320 kbps', size: '~10 MB' }
  ]
};

function renderQualities(list) {
  qualityGrid.innerHTML = '';
  list.forEach(function(q, i) {
    var div = document.createElement('div');
    div.className = 'quality-opt' + (i === 1 ? ' active' : '');
    div.dataset.quality = q.label;
    div.innerHTML = q.label + '<span class="q-size">' + q.size + '</span>';
    div.addEventListener('click', function() {
      qualityGrid.querySelectorAll('.quality-opt').forEach(function(o) {
        o.classList.remove('active');
      });
      div.classList.add('active');
      selectedQuality = q.label;
    });
    qualityGrid.appendChild(div);
  });
  selectedQuality = list[1].label;
}

formatChips.forEach(function(chip) {
  chip.addEventListener('click', function() {
    formatChips.forEach(function(c) { c.classList.remove('active'); });
    chip.classList.add('active');
    selectedFormat = chip.dataset.format;
    renderQualities(qualities[selectedFormat]);
    qualitySec.classList.add('visible');
  });
});

pasteBtn.addEventListener('click', function() {
  navigator.clipboard.readText().then(function(text) {
    urlInput.value = text;
    urlInput.focus();
  }).catch(function() {
    urlInput.focus();
  });
});

function isValidURL(url) {
  return /^(https?:\/\/)?(www\.)?(youtube\.com\/(watch\?v=|shorts\/)|youtu\.be\/)[\w\-]{11}/.test(url.trim());
}

function showError(msg) {
  errorText.textContent = msg;
  errorMsg.classList.add('visible');
}

function hideError() {
  errorMsg.classList.remove('visible');
}

downloadBtn.addEventListener('click', function() {
  hideError();
  resultCard.classList.remove('visible');

  var url = urlInput.value.trim();

  if (!url) return showError('Paste a YouTube link first.');
  if (!isValidURL(url)) return showError('Not a valid YouTube URL.');

  loadingText.textContent = 'Fetching video info...';
  loadingEl.classList.add('visible');
  downloadBtn.disabled = true;

  fetch(API_BASE + '/info', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: url })
  })
  .then(function(res) { return res.json(); })
  .then(function(infoData) {
    if (!infoData.success) throw new Error(infoData.error);

    loadingText.textContent = 'Preparing download link...';

    return fetch(API_BASE + '/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: url,
        format: selectedFormat,
        quality: selectedQuality
      })
    })
    .then(function(res) { return res.json(); })
    .then(function(dlData) {
      if (!dlData.success) throw new Error(dlData.error);

      var d = infoData.data;
      document.getElementById('resultTitle').textContent    = d.title;
      document.getElementById('resultChannel').textContent  = d.channel;
      document.getElementById('resultViews').textContent    = d.views;
      document.getElementById('resultDuration').textContent = d.duration;
      document.getElementById('resultThumb').src            = d.thumbnail;

      var dlLink = document.getElementById('downloadLink');
      dlLink.href = dlData.data.downloadUrl;
      dlLink.textContent = 'Download ' + selectedFormat.toUpperCase() + ' - ' + selectedQuality;

      loadingEl.classList.remove('visible');
      resultCard.classList.add('visible');
      resultCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  })
  .catch(function(err) {
    loadingEl.classList.remove('visible');
    showError(err.message || 'Something went wrong. Try again.');
  })
  .finally(function() {
    downloadBtn.disabled = false;
  });
});

document.getElementById('newSearchBtn').addEventListener('click', function() {
  resultCard.classList.remove('visible');
  urlInput.value = '';
  urlInput.focus();
});

urlInput.addEventListener('keydown', function(e) {
  if (e.key === 'Enter') downloadBtn.click();
});

renderQualities(qualities.mp4);