package hyperliquid

import "testing"

func TestDefaultBuilderIsDisabledInFork(t *testing.T) {
	if defaultBuilder != nil {
		t.Fatalf("defaultBuilder = %+v, want nil (builder fee disabled)", defaultBuilder)
	}
}
