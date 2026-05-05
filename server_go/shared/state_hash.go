package shared

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
)

func SnapshotHash(snapshot map[string]any) string {
	normalized := normalizeHashValue(snapshot)
	payload, err := json.Marshal(normalized)
	if err != nil {
		return ""
	}
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:12])
}

func normalizeHashValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		out := make(map[string]any, len(typed))
		for key, raw := range typed {
			if key == "server_time" {
				continue
			}
			out[key] = normalizeHashValue(raw)
		}
		return out
	case []any:
		out := make([]any, len(typed))
		for i, raw := range typed {
			out[i] = normalizeHashValue(raw)
		}
		return out
	case float64:
		return Round(typed, 4)
	case float32:
		return Round(float64(typed), 4)
	default:
		return value
	}
}
