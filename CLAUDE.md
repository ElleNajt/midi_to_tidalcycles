# midi_to_tidalcycles

Fork of [TylerMclaughlin/midi_to_tidalcycles](https://github.com/TylerMclaughlin/midi_to_tidalcycles) with multi-track support.

## Usage

```bash
python src/midi_to_tidalcycles.py [OPTIONS] <midi_file>
```

### Common options

- `-a` / `--amp` - Include velocity as `# amp` pattern
- `-l` / `--legato` - Include note duration as `# legato` pattern  
- `-c` / `--consolidate` - Use `!` notation for repeats (e.g., `~!4` instead of `~ ~ ~ ~`)
- `-H` / `--hide` - Hide info output (just print the Tidal code)
- `-q N` / `--resolution N` - Quanta per quarter note (default 8 = 32nd notes)
- `-1` / `--singletrack` - Original single-track mode (processes last track only)

### Examples

```bash
# Basic conversion with velocity and legato
python src/midi_to_tidalcycles.py -alc myfile.mid

# Quiet output (just the code, good for piping to file)
python src/midi_to_tidalcycles.py -alcH myfile.mid > output.tidal

# Lower resolution for simpler output (16th notes)
python src/midi_to_tidalcycles.py -alcH -q 4 myfile.mid
```

## Changes from upstream

1. **Multi-track by default** - Processes all tracks, outputs `d1`, `d2`, `d3`... for each
2. **32nd note resolution** - Default `-q 8` captures ornaments and fast runs
3. **No trailing silence** - Uses actual note end time instead of padding to full beats

## Dependencies

- numpy
- [python3-midi](https://github.com/louisabraham/python3-midi)

```bash
pip install numpy
git clone https://github.com/louisabraham/python3-midi
cd python3-midi && python setup.py install
```
