# Huffman Compression Tool

## What it is

A from-scratch Python implementation of Huffman coding for lossless file
compression, built with the standard library only — no external
dependencies. It goes beyond a textbook Huffman implementation by adding a
self-contained binary archive format, information-theory analysis, and a
proper command-line interface.

## Core features

- **Linear-time encoding**: uses list-based buffering rather than
  repeated string concatenation, avoiding an O(N²) anti-pattern that's
  common in naive Huffman implementations, keeping encoding at O(N).
- **Self-contained archives**: the compressed output embeds a serialized
  JSON header containing the frequency/tree data needed to decompress, so
  a compressed file can be decompressed without needing the original file
  or an external frequency map.
- **Information-theory analysis**: an optional verbose mode computes
  Shannon entropy for the input and compares the actual compression ratio
  achieved against the theoretical compression limit implied by that
  entropy — useful for understanding how close the implementation gets to
  optimal.
- **CLI interface**: built with `argparse`, supporting explicit `compress`
  and `decompress` subcommands.
- **Type-hinted throughout** for maintainability.

## Usage

Compress a file (with entropy/efficiency statistics):
```
python huffman_pro.py compress big_file.txt --verbose
```

Decompress a file:
```
python huffman_pro.py decompress big_file.bin
```

## Complexity

- Time: O(N log K), where N is file size and K is the number of unique
  symbols/characters in the input.
- Space: O(K) to store the Huffman tree.

## Requirements

Python 3.6+. No external libraries — standard library only.

## Out of scope

This is a single-file compression utility, not a general-purpose archive
format — it does not support multi-file archives, streaming/chunked
compression of very large files, or compatibility with standard formats
like gzip/zip.
