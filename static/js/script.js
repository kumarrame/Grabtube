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
var currentVideoUrl = '';

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

// Render quality options
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

// Format chip selection
formatChips.forEach(function(chip) {
  chip.addEventListener('click', function() {
    formatChips.forEach(function(c) { c.classList.remove('active'); });
    chip.classList.add('active');
    selectedFormat = chip.dataset.format;
    renderQualities(qualities[selectedFormat]);
    qualitySec.classList.add('visible');
  });
});

// Paste button
pasteBtn.addEventListener('click', function() {
  if (navigator.clipboard && navigator.clipboard.readText) {
    navigator.clipboard.readText().then(function(text) {
      urlInput.value = text;
      urlInput.focus();
    }).catch(function() {
      urlInput.focus();
    });
  } else {
    urlInput.focus();
    urlInput.select();
  }
});

// URL validation
function isValidURL(url) {
  return /^(https?:\/\/)?(www\.)?(youtube\.com\/(watch\?v=|shorts\/)|youtu\.be\/)[\w\-]{11}/.test(url.trim());
}

// Show/hide error
function showError(msg) {
  errorText.textContent = msg;
  errorMsg.classList.add('visible');
}

function hideError() {
  errorMsg.classList.remove('visible');
}

// Fetch with timeout
function fetchWithTimeout(url, options, timeoutMs) {
  timeoutMs = timeoutMs || 30000;
  return new Promise(function(resolve, reject) {
    var controller = null;
    var timeoutId = null;

    if (window.AbortController) {
      controller = new AbortController();
      options.signal = controller.signal;
      timeoutId = setTimeout(function() {
        controller.abort();
      }, timeoutMs);
    }

    fetch(url, options)
      .then(function(res) {
        if (timeoutId) clearTimeout(timeoutId);
        resolve(res);
      })
      .catch(function(err) {
        if (timeoutId) clearTimeout(timeoutId);
        if (err.name === 'AbortError') {
          reject(new Error('Request timed out. Please try again.'));
        } else {
          reject(err);
        }
      });
  });
}

// Main download button handler
downloadBtn.addEventListener('click', function() {
  hideError();
  resultCard.classList.remove('visible');

  var url = urlInput.value.trim();

  if (!url) return showError('Paste a YouTube link first.');
  if (!isValidURL(url)) return showError('Not a valid YouTube URL.');

  currentVideoUrl = url;
  loadingText.textContent = 'Fetching video info...';
  loadingEl.classList.add('visible');
  downloadBtn.disabled = true;

  fetchWithTimeout(API_BASE + '/info', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: url })
  }, 30000)
  .then(function(res) { return res.json(); })
  .then(function(data) {
    if (!data.success) throw new Error(data.error);

    var d = data.data;
    document.getElementById('resultTitle').textContent    = d.title;
    document.getElementById('resultChannel').textContent  = d.channel;
    document.getElementById('resultViews').textContent    = d.views;
    document.getElementById('resultDuration').textContent = d.duration;
    document.getElementById('resultThumb').src            = d.thumbnail;

    // Set download link - if formats available, use first matching format
    var dlLink = document.getElementById('downloadLink');

    if (d.formats && d.formats.length > 0) {
      // Find best matching format
      var matchingFormat = findBestFormat(d.formats, selectedFormat, selectedQuality);
      if (matchingFormat) {
        dlLink.href = matchingFormat.downloadUrl || '#';
        dlLink.textContent = 'Download ' + selectedFormat.toUpperCase() + ' - ' + selectedQuality;
        dlLink.onclick = function(e) {
          if (this.href === '#') {
            e.preventDefault();
            fetchDownloadUrl(url);
          }
        };
      } else {
        // No matching format, need to fetch download URL
        dlLink.href = '#';
        dlLink.textContent = 'Download ' + selectedFormat.toUpperCase() + ' - ' + selectedQuality;
        dlLink.onclick = function(e) {
          e.preventDefault();
          fetchDownloadUrl(url);
        };
      }
    } else {
      // No formats from info, need to fetch download URL
      dlLink.href = '#';
      dlLink.textContent = 'Download ' + selectedFormat.toUpperCase() + ' - ' + selectedQuality;
      dlLink.onclick = function(e) {
        e.preventDefault();
        fetchDownloadUrl(url);
      };
    }

    loadingEl.classList.remove('visible');
    resultCard.classList.add('visible');
    resultCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
  })
  .catch(function(err) {
    loadingEl.classList.remove('visible');
    showError(err.message || 'Something went wrong. Try again.');
  })
  .finally(function() {
    downloadBtn.disabled = false;
  });
});

// Find best matching format from available formats
function findBestFormat(formats, fmt, quality) {
  var targetHeight = 720;
  var heightMatch = quality.match(/(\d+)/);
  if (heightMatch) {
    targetHeight = parseInt(heightMatch[1]);
  }

  if (fmt === 'mp3') {
    // Find best audio format
    var bestAudio = null;
    var bestBitrate = 0;
    formats.forEach(function(f) {
      if (f.has_audio && !f.has_video) {
        var brMatch = f.quality.match(/(\d+)/);
        if (brMatch) {
          var br = parseInt(brMatch[1]);
          if (br > bestBitrate) {
            bestBitrate = br;
            bestAudio = f;
          }
        }
      }
    });
    return bestAudio;
  } else {
    // Find best video format matching quality
    var bestVideo = null;
    var bestDiff = Infinity;
    formats.forEach(function(f) {
      if (f.has_video) {
        var hMatch = f.quality.match(/(\d+)/);
        if (hMatch) {
          var h = parseInt(hMatch[1]);
          var diff = Math.abs(h - targetHeight);
          if (diff < bestDiff) {
            bestDiff = diff;
            bestVideo = f;
          }
        }
      }
    });
    return bestVideo;
  }
}

// Fetch download URL from API
function fetchDownloadUrl(url) {
  loadingText.textContent = 'Preparing download link...';
  loadingEl.classList.add('visible');

  fetchWithTimeout(API_BASE + '/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      url: url,
      format: selectedFormat,
      quality: selectedQuality
    })
  }, 45000)
  .then(function(res) { return res.json(); })
  .then(function(data) {
    if (!data.success) throw new Error(data.error);

    var dlLink = document.getElementById('downloadLink');
    dlLink.href = data.data.downloadUrl;
    dlLink.textContent = 'Download ' + selectedFormat.toUpperCase() + ' - ' + selectedQuality;
    dlLink.onclick = null;

    loadingEl.classList.remove('visible');
  })
  .catch(function(err) {
    loadingEl.classList.remove('visible');
    showError(err.message || 'Could not get download link. Try again.');
  });
}

// New search button
document.getElementById('newSearchBtn').addEventListener('click', function() {
  resultCard.classList.remove('visible');
  urlInput.value = '';
  currentVideoUrl = '';
  urlInput.focus();
});

// Enter key to submit
urlInput.addEventListener('keydown', function(e) {
  if (e.key === 'Enter') downloadBtn.click();
});

// Contact form handler
var contactForm = document.getElementById('contactForm');
if (contactForm) {
  contactForm.addEventListener('submit', function(e) {
    e.preventDefault();

    var name = document.getElementById('contactName').value.trim();
    var email = document.getElementById('contactEmail').value.trim();
    var message = document.getElementById('contactMsg').value.trim();
    var btn = contactForm.querySelector('button');
    var btnText = btn.textContent;

    if (!name || !email || !message) {
      alert('Please fill in all fields.');
      return;
    }

    if (email.indexOf('@') === -1) {
      alert('Please enter a valid email.');
      return;
    }

    btn.disabled = true;
    btn.textContent = 'Sending...';

    fetchWithTimeout(API_BASE + '/contact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name, email: email, message: message })
    }, 15000)
    .then(function(res) { return res.json(); })
    .then(function(data) {
      if (!data.success) throw new Error(data.error);
      alert(data.message || 'Message sent successfully!');
      contactForm.reset();
    })
    .catch(function(err) {
      alert(err.message || 'Failed to send. Please try again.');
    })
    .finally(function() {
      btn.disabled = false;
      btn.textContent = btnText;
    });
  });
}

// Initialize quality options
renderQualities(qualities.mp4);
