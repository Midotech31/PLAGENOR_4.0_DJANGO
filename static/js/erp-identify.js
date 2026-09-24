(() => {
  'use strict';
  const printButton = document.getElementById('print-labels');
  if (printButton) printButton.addEventListener('click', () => window.print());
  const root = document.getElementById('camera-scanner');
  if (!root) return;
  const video = document.getElementById('identity-video');
  const start = document.getElementById('camera-start');
  const stopButton = document.getElementById('camera-stop');
  const status = document.getElementById('camera-status');
  let stream = null;
  let timer = null;
  let generation = 0;
  const stop = () => {
    generation += 1;
    if (timer !== null) window.clearTimeout(timer);
    timer = null;
    if (stream) stream.getTracks().forEach(track => track.stop());
    stream = null;
    video.srcObject = null;
    video.hidden = true;
    stopButton.hidden = true;
    start.disabled = false;
  };
  stopButton.addEventListener('click', stop);
  window.addEventListener('pagehide', stop);
  if (!window.BarcodeDetector || !navigator.mediaDevices?.getUserMedia) {
    start.disabled = true;
    status.textContent = root.dataset.noCamera;
    return;
  }
  start.addEventListener('click', async () => {
    start.disabled = true;
    const current = ++generation;
    try {
      const supported = await window.BarcodeDetector.getSupportedFormats();
      const formats = ['qr_code', 'data_matrix', 'code_128', 'ean_13'].filter(format => supported.includes(format));
      if (!formats.length) { stop(); status.textContent = root.dataset.noCamera; return; }
      const detector = new window.BarcodeDetector({formats});
      const opened = await navigator.mediaDevices.getUserMedia({video: {facingMode: {ideal: 'environment'}}, audio: false});
      if (current !== generation) { opened.getTracks().forEach(track => track.stop()); return; }
      stream = opened;
      video.srcObject = stream;
      video.hidden = false;
      stopButton.hidden = false;
      await video.play();
      status.textContent = root.dataset.cameraReady;
      const scan = async () => {
        if (current !== generation || !stream) return;
        try {
          const codes = await detector.detect(video);
          if (codes.length && codes[0].rawValue && codes[0].rawValue.length <= 255) {
            const value = codes[0].rawValue;
            stop();
            document.getElementById('identity-query').value = value;
            document.getElementById('identity-search').requestSubmit();
            return;
          }
        } catch (_) {
          if (current !== generation) return;
        }
        timer = window.setTimeout(scan, 250);
      };
      scan();
    } catch (_) {
      stop();
      status.textContent = root.dataset.cameraError;
    }
  });
})();
