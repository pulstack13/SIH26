// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract GarudaAudit {
    /// @dev The only outcomes produced by the capture-quality prototype.
    enum CaptureStatus { READY, RECAPTURE }

    event ScanRecorded(
        string reportId,
        bytes32 evidenceHash,
        CaptureStatus status,
        uint256 timestamp,
        address indexed recordedBy
    );

    function recordScan(
        string calldata reportId,
        bytes32 evidenceHash,
        CaptureStatus status,
        uint256 timestamp
    ) external {
        emit ScanRecorded(reportId, evidenceHash, status, timestamp, msg.sender);
    }
}
