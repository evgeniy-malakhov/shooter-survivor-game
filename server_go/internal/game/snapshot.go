package game

import "neonoutbreak/server_go/shared"

func CompactSnapshot(snapshot Snapshot, localPlayerID string, interestRadius float64) map[string]any {
	return shared.CompactSnapshot(snapshot, localPlayerID, interestRadius)
}
