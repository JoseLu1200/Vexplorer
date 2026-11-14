/** A workspace tool hosted inside the current shell, preserving the active run. */
export function createReconstructionPanel() {
  const dialog = document.createElement('dialog');
  dialog.className = 'construction-dialog';
  dialog.setAttribute('aria-labelledby', 'construction-dialog-title');
  const header = document.createElement('header');
  const title = document.createElement('h2');
  title.id = 'construction-dialog-title';
  title.textContent = 'Construcción por piezas';
  const close = document.createElement('button');
  close.className = 'button';
  close.textContent = 'Volver al plano';
  close.type = 'button';
  close.addEventListener('click', () => dialog.close());
  const frame = document.createElement('iframe');
  frame.title = 'Propuesta paramétrica y aclaraciones';
  header.append(title, close);
  dialog.append(header, frame);
  document.body.append(dialog);
  let runId, trigger;
  dialog.addEventListener('close', () => trigger?.focus());
  window.addEventListener('message', event => {
    if (event.origin === location.origin && event.source === frame.contentWindow &&
        event.data?.type === 'reconstruction-close') dialog.close();
  });
  return {
    open(id, button) {
      trigger = button;
      if (id !== runId) {
        runId = id;
        frame.src = `./reconstruction.html?run=${encodeURIComponent(id)}&embedded=1`;
      } else {
        frame.contentWindow?.postMessage({type:'reconstruction-theme',theme:document.documentElement.dataset.theme ?? 'light'}, location.origin);
      }
      if (!dialog.open) dialog.showModal();
      close.focus();
    },
  };
}
