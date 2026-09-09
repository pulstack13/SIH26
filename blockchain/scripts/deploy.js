const hre = require("hardhat");

async function main() {
  const Audit = await hre.ethers.getContractFactory("GarudaAudit");
  const audit = await Audit.deploy();
  await audit.waitForDeployment();
  console.log(`GARUDA_AUDIT_CONTRACT=${await audit.getAddress()}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
