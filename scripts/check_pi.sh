#!/bin/bash

if command -v pi &> /dev/null; then
    echo "pi found: $(which pi)"
    pi --version 2>/dev/null || true
    exit 0
else
    echo "pi not found in PATH"
    echo "Please install Pi:"
    echo "  npm i -g @earendil-works/pi-coding-agent"
    exit 1
fi
