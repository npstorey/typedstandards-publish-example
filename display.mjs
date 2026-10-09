// Reads every record an index lists through host-policy.json, with host-core's
// display seam, and prints how each is displayed. The index is the path given as the
// first argument, docs/records.json by default: publish.yml passes the index it built.
// It exits 1 when the policy refuses a record: a status no rule names, a signer or
// type the policy does not name, or a record no rule matches. It renders nothing.
import { readFileSync } from 'node:fs';
import { displayOf, parseIndex, parsePolicy } from '@typedstandards/host-core';

const policy = parsePolicy(JSON.parse(readFileSync('host-policy.json', 'utf8')));
const indexPath = process.argv[2] ?? 'docs/records.json';
const index = parseIndex(JSON.parse(readFileSync(indexPath, 'utf8')));

let refused = 0;
for (const record of index.records) {
  try {
    const shown = displayOf(record, policy);
    console.log(`${record.name}: ${record.status}, displayed as ${shown.as} (rule ${shown.rule})`);
  } catch (err) {
    refused += 1;
    console.log(`${record.name}: ${record.status}, refused: ${err instanceof Error ? err.message : String(err)}`);
  }
}
console.log(`display: ${index.records.length} listed, ${refused} refused`);
process.exitCode = refused === 0 ? 0 : 1;
