// SPDX-License-Identifier: MIT
const {webFrame} = require('electron');
const fs = require('node:fs');
const path = require('node:path');

window.bundleCheck = new Promise((resolve, reject) => {
  window.addEventListener('DOMContentLoaded', () => {
    try {
      const WebView = window.customElements.get('webview');
      if (typeof WebView !== 'function' || window.WebView !== WebView) {
        throw new Error('Generated bundle did not register WebView');
      }
      if (typeof WebView.prototype.loadURL !== 'function') {
        throw new Error('Generated forwarding methods missing');
      }
      if ('connectedCallback' in WebView.prototype || 'observedAttributes' in WebView) {
        throw new Error('Internal lifecycle hooks leaked');
      }
      let guarded = false;
      try {
        WebView.prototype.getWebContentsId.call(document.createElement('div'));
      } catch (error) {
        guarded = error.message.includes('must be attached');
      }
      if (!guarded) throw new Error('Unattached WebView access was not rejected');
      document.querySelector('h1').textContent = 'Generated bundle works';
      resolve('registered-and-guarded');
    } catch (error) { reject(error); }
  }, {once: true});
  const source = fs.readFileSync(path.join(__dirname, 'isolated_bundle.js'), 'utf8');
  new Function('isolatedApi', source)({
    // Registration installs methods; guest creation is outside this smoke.
    guestViewInternal: {},
    allowGuestViewElementDefinition: (target, callback) => webFrame.allowGuestViewElementDefinition(target, callback),
  });
});
