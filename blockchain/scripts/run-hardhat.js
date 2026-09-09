// Keep Hardhat's mutable runtime state project-local. This avoids failures when
// the Windows global Hardhat config directory is unavailable or malformed.
const path = require("path");

const runtimeDirectory = path.join(__dirname, "..", ".hardhat-runtime");
process.env.APPDATA = runtimeDirectory;
process.env.LOCALAPPDATA = runtimeDirectory;
require("hardhat/internal/cli/cli");
