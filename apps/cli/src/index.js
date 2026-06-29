#!/usr/bin/env node

const VERSION = "0.1.0";

const command = process.argv[2];

function printHelp() {
  console.log(`ScholarFlow CLI ${VERSION}

Usage:
  scholarflow --version
  scholarflow status

Phase 1 provides the CLI entry only. Workspace commands will be added in Phase 4.`);
}

switch (command) {
  case "--version":
  case "-v":
    console.log(VERSION);
    break;
  case "status":
    console.log("ScholarFlow CLI skeleton is ready. Runtime workspace commands are planned for Phase 4.");
    break;
  case undefined:
  case "--help":
  case "-h":
    printHelp();
    break;
  default:
    console.error(`Unknown command: ${command}`);
    printHelp();
    process.exitCode = 1;
}

