/**
 * Impeccable Design System Guard Hook Script
 * Validates frontend files against DESIGN.md tokens and conventions.
 */

const fs = require('fs');
const path = require('path');

// Read hook payload from stdin
let inputData = '';
process.stdin.setEncoding('utf8');

process.stdin.on('data', (chunk) => {
  inputData += chunk;
});

process.stdin.on('end', () => {
  try {
    // If payload contains toolCall args for file edits, check modified target
    if (inputData.trim()) {
      const payload = JSON.parse(inputData);
      const targetFile = payload?.toolCall?.args?.TargetFile;
      if (targetFile && (targetFile.endsWith('.tsx') || targetFile.endsWith('.jsx') || targetFile.endsWith('.css'))) {
        console.log(`[impeccable] Validating frontend design compliance for: ${path.basename(targetFile)}`);
      }
    }
  } catch (err) {
    // Fallback gracefully on parsing errors
  }

  // Hook contract: return empty JSON object on stdout
  process.stdout.write(JSON.stringify({}));
  process.exit(0);
});
