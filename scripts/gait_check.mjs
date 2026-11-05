#!/usr/bin/env node
// node scripts/gait_check.mjs <model.bbmodel> <animation name> [samples]  -> JSON {animation, legs:[{bone, peak_while, range, ok}]}
import {readFileSync} from 'node:fs';
import {gaitReport} from '../tools/blockbench-mcp-safe/src/gait.mjs';
const [file, clip, samples] = process.argv.slice(2);
console.log(JSON.stringify({animation: clip, legs: gaitReport(JSON.parse(readFileSync(file, 'utf8')), clip, Number(samples || 16))}));
