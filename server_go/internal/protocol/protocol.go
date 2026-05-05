package protocol

import (
	"bufio"
	"bytes"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
)

const (
	MaxMessageBytes = 2_000_000
	ProtocolVersion = 2
	SnapshotSchema  = "compact-v1"
	ServerVersion   = "go-0.1.0"
)

var ServerFeatures = []string{
	"commands",
	"input_ack",
	"client_prediction",
	"interpolation",
	"adaptive_snapshot",
	"resume_session",
	"health_probe",
	"metrics_http",
	"go_runtime",
}

type Message map[string]any

func Encode(messageType string, fields Message) ([]byte, error) {
	if fields == nil {
		fields = Message{}
	}
	fields["type"] = messageType
	body, err := json.Marshal(fields)
	if err != nil {
		return nil, err
	}
	if len(body) > MaxMessageBytes {
		return nil, fmt.Errorf("message too large: %d", len(body))
	}
	frame := make([]byte, 4+len(body))
	binary.BigEndian.PutUint32(frame[:4], uint32(len(body)))
	copy(frame[4:], body)
	return frame, nil
}

type Reader struct {
	r *bufio.Reader
}

func NewReader(r io.Reader) *Reader {
	return &Reader{r: bufio.NewReaderSize(r, 64*1024)}
}

func (r *Reader) Read() (Message, error) {
	header := make([]byte, 4)
	if _, err := io.ReadFull(r.r, header); err != nil {
		return nil, err
	}
	size := binary.BigEndian.Uint32(header)
	if size == 0 || size > MaxMessageBytes {
		return nil, fmt.Errorf("invalid frame size %d", size)
	}
	payload := make([]byte, size)
	if _, err := io.ReadFull(r.r, payload); err != nil {
		return nil, err
	}
	return DecodePayload(payload)
}

func DecodePayload(payload []byte) (Message, error) {
	payload = bytes.TrimSpace(payload)
	if len(payload) == 0 {
		return nil, errors.New("empty message")
	}
	if payload[0] == '{' {
		var msg Message
		if err := json.Unmarshal(payload, &msg); err != nil {
			return nil, err
		}
		if _, ok := msg["type"]; !ok {
			return nil, errors.New("missing message type")
		}
		return msg, nil
	}
	decoded, err := decodeMsgpack(payload)
	if err != nil {
		return nil, err
	}
	msg, ok := decoded.(map[string]any)
	if !ok {
		return nil, errors.New("msgpack root is not a map")
	}
	if _, ok := msg["type"]; !ok {
		return nil, errors.New("missing message type")
	}
	return msg, nil
}

type msgpackDecoder struct {
	data []byte
	pos  int
}

func decodeMsgpack(data []byte) (any, error) {
	d := &msgpackDecoder{data: data}
	value, err := d.read()
	if err != nil {
		return nil, err
	}
	return value, nil
}

func (d *msgpackDecoder) read() (any, error) {
	if d.pos >= len(d.data) {
		return nil, io.ErrUnexpectedEOF
	}
	code := d.byte()
	switch {
	case code <= 0x7f:
		return int64(code), nil
	case code >= 0x80 && code <= 0x8f:
		return d.readMap(int(code & 0x0f))
	case code >= 0x90 && code <= 0x9f:
		return d.readArray(int(code & 0x0f))
	case code >= 0xa0 && code <= 0xbf:
		return d.readString(int(code & 0x1f))
	case code >= 0xe0:
		return int64(int8(code)), nil
	}
	switch code {
	case 0xc0:
		return nil, nil
	case 0xc2:
		return false, nil
	case 0xc3:
		return true, nil
	case 0xc4:
		return d.readBinary(int(d.u8()))
	case 0xc5:
		return d.readBinary(int(d.u16()))
	case 0xc6:
		return d.readBinary(int(d.u32()))
	case 0xca:
		return float64(math.Float32frombits(d.u32())), nil
	case 0xcb:
		return math.Float64frombits(d.u64()), nil
	case 0xcc:
		return int64(d.u8()), nil
	case 0xcd:
		return int64(d.u16()), nil
	case 0xce:
		return int64(d.u32()), nil
	case 0xcf:
		return int64(d.u64()), nil
	case 0xd0:
		return int64(int8(d.u8())), nil
	case 0xd1:
		return int64(int16(d.u16())), nil
	case 0xd2:
		return int64(int32(d.u32())), nil
	case 0xd3:
		return int64(d.u64()), nil
	case 0xd9:
		return d.readString(int(d.u8()))
	case 0xda:
		return d.readString(int(d.u16()))
	case 0xdb:
		return d.readString(int(d.u32()))
	case 0xdc:
		return d.readArray(int(d.u16()))
	case 0xdd:
		return d.readArray(int(d.u32()))
	case 0xde:
		return d.readMap(int(d.u16()))
	case 0xdf:
		return d.readMap(int(d.u32()))
	default:
		return nil, fmt.Errorf("unsupported msgpack code 0x%x", code)
	}
}

func (d *msgpackDecoder) readMap(n int) (map[string]any, error) {
	out := make(map[string]any, n)
	for i := 0; i < n; i++ {
		key, err := d.read()
		if err != nil {
			return nil, err
		}
		value, err := d.read()
		if err != nil {
			return nil, err
		}
		out[fmt.Sprint(key)] = value
	}
	return out, nil
}

func (d *msgpackDecoder) readArray(n int) ([]any, error) {
	out := make([]any, n)
	for i := range out {
		value, err := d.read()
		if err != nil {
			return nil, err
		}
		out[i] = value
	}
	return out, nil
}

func (d *msgpackDecoder) readString(n int) (string, error) {
	if d.pos+n > len(d.data) {
		return "", io.ErrUnexpectedEOF
	}
	value := string(d.data[d.pos : d.pos+n])
	d.pos += n
	return value, nil
}

func (d *msgpackDecoder) readBinary(n int) ([]byte, error) {
	if d.pos+n > len(d.data) {
		return nil, io.ErrUnexpectedEOF
	}
	value := append([]byte(nil), d.data[d.pos:d.pos+n]...)
	d.pos += n
	return value, nil
}

func (d *msgpackDecoder) byte() byte {
	b := d.data[d.pos]
	d.pos++
	return b
}

func (d *msgpackDecoder) u8() uint8 {
	return uint8(d.byte())
}

func (d *msgpackDecoder) u16() uint16 {
	if d.pos+2 > len(d.data) {
		d.pos = len(d.data)
		return 0
	}
	v := binary.BigEndian.Uint16(d.data[d.pos : d.pos+2])
	d.pos += 2
	return v
}

func (d *msgpackDecoder) u32() uint32 {
	if d.pos+4 > len(d.data) {
		d.pos = len(d.data)
		return 0
	}
	v := binary.BigEndian.Uint32(d.data[d.pos : d.pos+4])
	d.pos += 4
	return v
}

func (d *msgpackDecoder) u64() uint64 {
	if d.pos+8 > len(d.data) {
		d.pos = len(d.data)
		return 0
	}
	v := binary.BigEndian.Uint64(d.data[d.pos : d.pos+8])
	d.pos += 8
	return v
}

func String(v any, fallback string) string {
	if s, ok := v.(string); ok {
		return s
	}
	return fallback
}

func Float(v any, fallback float64) float64 {
	switch x := v.(type) {
	case float64:
		return x
	case float32:
		return float64(x)
	case int:
		return float64(x)
	case int64:
		return float64(x)
	case uint64:
		return float64(x)
	case json.Number:
		f, _ := x.Float64()
		return f
	default:
		return fallback
	}
}

func Int(v any, fallback int) int {
	return int(Float(v, float64(fallback)))
}

func Bool(v any, fallback bool) bool {
	if b, ok := v.(bool); ok {
		return b
	}
	return fallback
}
