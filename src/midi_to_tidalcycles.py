from __future__ import print_function

import argparse

import midi
import numpy as np


def midinote_to_note_name(midi_note, strudel_mode=False):
    if midi_note == 0.0:
        return "~"
    midi_note = int(midi_note)
    note_names_array = ["c", "cs", "d", "ds", "e", "f", "fs", "g", "gs", "a", "as", "b"]
    if strudel_mode:
        note_names_array = [
            "c",
            "db",
            "d",
            "eb",
            "e",
            "f",
            "gb",
            "g",
            "ab",
            "a",
            "bb",
            "b",
        ]

    q, r = divmod(midi_note, 12)
    note_name = note_names_array[r]
    octave_name = q  # q - 1  <- this is correct but tidal is off by an octave I think.
    full_note_name = str(note_name) + str(octave_name)
    return full_note_name


def midinote_to_scale_degree(midi_note, scale_list, z=12):
    if midi_note == 0.0:
        return "~"
    midi_note = int(midi_note) - 60
    # for non-12-TET scales, z may not be 12.
    q, r = divmod(midi_note, z)
    scale_degree = q * len(scale_list) + scale_list.index(r)
    return scale_degree


def assert_end_of_track(midi_pattern):
    last_event = midi_pattern[-1][-1]
    assert type(last_event) == midi.events.EndOfTrackEvent


def get_event_type(event):
    if type(event) == midi.events.NoteOnEvent:
        if event.velocity != 0:
            event_type = "note_on_event"
        # MIDI has a formatting quirk where noteOff events
        # can also be encoded as NoteOn with velocity 0
        elif event.velocity == 0:
            event_type = "note_off_event"
    elif type(event) == midi.events.NoteOffEvent:
        event_type = "note_off_event"
    else:
        event_type = "unknown"
    return event_type


def infer_polyphony(midi_pattern):
    assert_end_of_track(midi_pattern)
    n_adjacent_on_events = 0
    inferred_polyphony = 0
    for index, event in enumerate(midi_pattern[-1]):
        event_type = get_event_type(event)
        if event_type == "note_on_event":  # starting note on
            n_adjacent_on_events += 1
            inferred_polyphony = max(inferred_polyphony, n_adjacent_on_events)
        elif event_type == "note_off_event":
            n_adjacent_on_events = 0
    return inferred_polyphony


def infer_polyphony_for_track(track):
    """Infer polyphony for a single track."""
    n_adjacent_on_events = 0
    inferred_polyphony = 0
    for event in track:
        event_type = get_event_type(event)
        if event_type == "note_on_event":
            n_adjacent_on_events += 1
            inferred_polyphony = max(inferred_polyphony, n_adjacent_on_events)
        elif event_type == "note_off_event":
            n_adjacent_on_events = 0
    return inferred_polyphony


def get_track_name(track):
    """Extract track name from track events."""
    for event in track:
        if hasattr(event, "text") and type(event).__name__ == "TrackNameEvent":
            return event.text
        if hasattr(event, "text") and type(event).__name__ == "InstrumentNameEvent":
            return event.text
    return None


def track_has_notes(track):
    """Check if a track contains any note events."""
    for event in track:
        if get_event_type(event) == "note_on_event":
            return True
    return False


def midi_to_array(
    filename,
    quanta_per_qn=4,
    velocity_on=False,
    legato_on=False,
    print_events=False,
    debug=False,
    hide=False,
):
    pattern = midi.read_midifile(filename)

    ticks_per_quanta = (
        pattern.resolution / quanta_per_qn
    )  # = ticks per quarter note * quarter note per quanta
    last_event = pattern[-1][-1]
    assert type(last_event) == midi.events.EndOfTrackEvent
    cum_ticks = 0
    for index, event in enumerate(pattern[-1]):
        cum_ticks += event.tick
    ticks_per_beat = pattern.resolution * 4
    pretail_total_beats = cum_ticks / float(ticks_per_beat)
    total_beats = int(np.ceil(pretail_total_beats))
    real_total_ticks = total_beats * ticks_per_beat
    # this int() is just for type matching in python 3 and shouldn't be rounding anything--
    # n_quanta should already be an int.
    n_quanta = int(real_total_ticks / ticks_per_quanta)
    polyphony = infer_polyphony(pattern)
    if not hide:
        print("inferred polyphony is ", end="")
        print(polyphony)
    note_vector = np.zeros((n_quanta, polyphony))
    if velocity_on:
        velocity_vector = np.zeros((n_quanta, polyphony))
    if legato_on:
        legato_vector = np.zeros((n_quanta, polyphony))
        currently_active_notes = {}
    cum_ticks = 0
    voice = -1
    for event in pattern[-1]:
        event_type = get_event_type(event)
        if print_events or debug:
            print(event)
        cum_ticks += event.tick
        if event_type == "note_on_event":
            voice += 1
            quanta_index = int(cum_ticks / ticks_per_quanta)
            if debug:
                print("voice number ", end="")
                print(voice)
                print("quanta number ", end="")
                print(quanta_index)
            note_vector[quanta_index, voice] = event.pitch
            if legato_on:
                currently_active_notes[event.pitch] = [quanta_index, voice]
            if velocity_on:
                velocity_vector[quanta_index, voice] = event.velocity
        elif (event_type == "note_off_event") & (legato_on):
            quanta_note_off_index = int(cum_ticks / ticks_per_quanta)
            note_length = quanta_note_off_index - currently_active_notes[event.pitch][0]
            legato_vector[
                currently_active_notes[event.pitch][0],
                currently_active_notes[event.pitch][1],
            ] = note_length
            del currently_active_notes[event.pitch]
            voice = -1  # -= 1
        else:  # end of track
            # turn all notes off
            quanta_note_off_index = int(cum_ticks / ticks_per_quanta)
            if legato_on:
                for key in currently_active_notes.keys():
                    note_length = quanta_note_off_index - currently_active_notes[key][0]
                    legato_vector[currently_active_notes[key], voice] = note_length
            voice = -1
    if not legato_on and velocity_on:
        return note_vector, velocity_vector

    elif not velocity_on and legato_on:
        return note_vector, legato_vector

    elif velocity_on and legato_on:
        return note_vector, velocity_vector, legato_vector

    else:
        return note_vector


def midi_to_multitrack_arrays(
    filename,
    quanta_per_qn=4,
    velocity_on=False,
    legato_on=False,
    print_events=False,
    debug=False,
    hide=False,
):
    """
    Process all tracks in a MIDI file, returning a list of track data.
    Each track becomes a separate entry with its own note/velocity/legato arrays.
    """
    pattern = midi.read_midifile(filename)
    ticks_per_quanta = pattern.resolution / quanta_per_qn
    ticks_per_beat = pattern.resolution * 4

    # Find total length across all tracks
    max_cum_ticks = 0
    for track in pattern:
        cum_ticks = 0
        for event in track:
            cum_ticks += event.tick
        max_cum_ticks = max(max_cum_ticks, cum_ticks)

    pretail_total_beats = max_cum_ticks / float(ticks_per_beat)
    total_beats = int(np.ceil(pretail_total_beats))
    real_total_ticks = total_beats * ticks_per_beat
    n_quanta = int(real_total_ticks / ticks_per_quanta)

    tracks_data = []

    for track_idx, track in enumerate(pattern):
        if not track_has_notes(track):
            continue

        track_name = get_track_name(track) or f"Track {track_idx}"
        polyphony = infer_polyphony_for_track(track)

        if polyphony == 0:
            continue

        if not hide:
            print(f"Track {track_idx}: {track_name}, polyphony: {polyphony}")

        note_vector = np.zeros((n_quanta, polyphony))
        velocity_vector = np.zeros((n_quanta, polyphony)) if velocity_on else None
        legato_vector = np.zeros((n_quanta, polyphony)) if legato_on else None
        currently_active_notes = {} if legato_on else None

        cum_ticks = 0
        voice = -1

        for event in track:
            event_type = get_event_type(event)
            if print_events or debug:
                print(event)
            cum_ticks += event.tick

            if event_type == "note_on_event":
                voice += 1
                if voice >= polyphony:
                    voice = polyphony - 1  # clamp to avoid index errors
                quanta_index = int(cum_ticks / ticks_per_quanta)
                if quanta_index >= n_quanta:
                    quanta_index = n_quanta - 1

                if debug:
                    print(f"voice {voice}, quanta {quanta_index}")

                note_vector[quanta_index, voice] = event.pitch
                if legato_on:
                    currently_active_notes[event.pitch] = [quanta_index, voice]
                if velocity_on:
                    velocity_vector[quanta_index, voice] = event.velocity

            elif event_type == "note_off_event":
                if legato_on and event.pitch in currently_active_notes:
                    quanta_note_off_index = int(cum_ticks / ticks_per_quanta)
                    if quanta_note_off_index >= n_quanta:
                        quanta_note_off_index = n_quanta - 1
                    note_length = (
                        quanta_note_off_index - currently_active_notes[event.pitch][0]
                    )
                    legato_vector[
                        currently_active_notes[event.pitch][0],
                        currently_active_notes[event.pitch][1],
                    ] = note_length
                    del currently_active_notes[event.pitch]
                voice = -1

        track_data = {
            "name": track_name,
            "track_idx": track_idx,
            "notes": note_vector,
            "velocities": velocity_vector,
            "legatos": legato_vector,
            "polyphony": polyphony,
        }
        tracks_data.append(track_data)

    return tracks_data, n_quanta


def vel_to_amp(vel):
    return round(vel / 127.0, 2)


def simplify_repeats(list_pattern, simplify_zeros=True):
    """
    Converts ['a', 'a', 'b', 'a', 'b', 'b', 'b'] to ['a!2', 'b', 'a', 'b!3']
    simplify_zeros (default) converts 0.0! to 0!
    """
    n_repeats = 0
    output_list = []
    for i, x in enumerate(list_pattern):
        # if not the last element
        if i != len(list_pattern) - 1:
            # if the next element is a repeat
            # increment the counter
            if x == list_pattern[i + 1]:
                n_repeats += 1
            # if next element is different and current element is not a repeat.
            elif n_repeats == 0:
                output_list.append(x)
            # otherwise there was a repeat that terminates now.
            else:
                new_x = str(x) + "!" + str(n_repeats + 1)
                output_list.append(new_x)
                n_repeats = 0
        # handle last element
        else:
            # simple case, last element is not a repeat
            if n_repeats == 0:
                output_list.append(x)
            # the penultimate position matches the last.
            else:
                new_x = str(x) + "!" + str(n_repeats + 1)
                output_list.append(new_x)
                n_repeats = 0

    if simplify_zeros:
        output_list = [str(x) for x in output_list]
        output_list = [
            x.replace("0.0!", "0!") if x.startswith("0.0!") else x for x in output_list
        ]
        output_list = [x.replace("0.0", "0") if x == "0.0" else x for x in output_list]
        # output_list = [x.replace('0.0!','0!') if isinstance(x, str) else x for x in output_list]
        # output_list = [x.replace(' 0.0 ',' 0 ') if isinstance(x, str) else x for x in output_list]
    return output_list


def print_tidal_midi_stack(
    notes, vels=None, legatos=None, consolidate=None, scale=False
):
    n_voices = len(notes[0, :])
    if scale:
        # just 12 tone for now
        scale_list = sorted(list(set([x % 12 for x in notes.flatten() if x != 0.0])))
        scale_pat = " ".join([str(int(x)) for x in scale_list])
    # determine whether a stack is needed and create a control boolean
    add_stack = (n_voices != 1) | (vels is not None) | (legatos is not None)
    if add_stack:
        print("stack [")
    # iterate over voices
    for j in range(0, n_voices):
        if not scale:
            notes_names = [midinote_to_note_name(x) for x in notes[:, j]]
        elif scale:
            notes_names = [midinote_to_scale_degree(x, scale_list) for x in notes[:, j]]
        if consolidate:
            notes_names = simplify_repeats(notes_names)
        if not scale:
            print('     n "', end="")
            print(*notes_names, sep=" ", end="")
        elif scale:
            print('     n (tScale "' + scale_pat + '" $ "', end="")
            print(*notes_names, sep=" ", end="")
        if (
            (legatos is None) & (vels is None) & (j != n_voices - 1)
        ):  # add a quote and a comma if there are more voices in the stack
            if not scale:
                print('",')
            elif scale:
                print('" ),')
        else:  # else this is the last voice, so just close the quotes
            if not scale:
                print('"')
            elif scale:
                print('" )')  # else this is the last voice, so close the quotes
        if vels is not None:
            print('     # amp "', end="")
            note_vels = [vel_to_amp(x) for x in vels[:, j]]
            if consolidate:
                note_vels = simplify_repeats(note_vels)
            print(*note_vels, sep=" ", end="")
            # add comma if it's not the last voice and if there are no legatos
            if legatos is None:
                if not j == len(notes[0, :]) - 1:
                    print('",')
                # otherwise close the stack
                else:
                    print('"\n     ]')
            else:  # if legatos is not None
                print('"')
        if legatos is not None:
            print('     # legato "', end="")
            note_legatos = [x for x in legatos[:, j]]
            if consolidate:
                note_legatos = simplify_repeats(note_legatos)
            print(*note_legatos, sep=" ", end="")
            # add comma if it's not the last voice
            if not j == len(notes[0, :]) - 1:
                print('",')
            # otherwise close the stack
            else:
                print('"\n     ]')
        if (legatos is None) & (vels is None) & (j == n_voices - 1) & (add_stack):
            print("     ]")


def print_tidal(_args, notes, vels, legatos):
    if _args.brackets:
        print(":{")
    # make a let statement
    if len(_args.name) != 0:
        print("let " + args.name + " = ", end="")

    # syncs tempo across all midis!
    slow_cmd = "slow (" + str(notes.shape[0] / _args.resolution) + "/4) $ "
    print(slow_cmd, end="")
    print_tidal_midi_stack(
        notes, vels, legatos, consolidate=_args.consolidate, scale=_args.scale
    )
    if _args.brackets:
        print(":}")


# strudel section


def print_strudel_notes(_args, notes, strudel_indent):
    notes = [midinote_to_note_name(l, strudel_mode=True) for l in list(notes)]
    if _args.consolidate:
        notes = simplify_repeats(notes)
        notes = " ".join(notes)
    print(f"{strudel_indent}note(`{notes}`)", end="")


def print_strudel_vels(_args, vels, strudel_indent="\n  "):
    if _args.amp:
        vels = [vel_to_amp(v) for v in vels]
        if _args.consolidate:
            vels = simplify_repeats(vels)
        fvels = " ".join([str(l) for l in vels])
        print(f"{strudel_indent}.gain(`{fvels}`)", end="")


def print_strudel_legatos(_args, legatos, strudel_indent="\n  "):
    if _args.legato:
        if _args.consolidate:
            legatos = simplify_repeats(legatos)
        flegatos = " ".join([str(l) for l in legatos])
        print(f"{strudel_indent}.legato(`{flegatos}`)", end="")


def print_tidal_multitrack(_args, tracks_data, n_quanta):
    """Print Tidal code for multi-track MIDI files."""
    print("do")
    for i, track in enumerate(tracks_data):
        notes = track["notes"]
        vels = track["velocities"]
        legatos = track["legatos"]
        track_name = track["name"]

        print(f"  -- {track_name}")

        # Build the pattern for this track
        slow_cmd = f"slow ({n_quanta / _args.resolution}/4) $ "

        n_voices = notes.shape[1]

        if n_voices == 1:
            # Single voice track
            notes_names = [midinote_to_note_name(x) for x in notes[:, 0]]
            if _args.consolidate:
                notes_names = simplify_repeats(notes_names)
            notes_str = " ".join(str(x) for x in notes_names)
            print(f'  d{i + 1} $ {slow_cmd}n "{notes_str}"')

            if vels is not None:
                note_vels = [vel_to_amp(x) for x in vels[:, 0]]
                if _args.consolidate:
                    note_vels = simplify_repeats(note_vels)
                vels_str = " ".join(str(x) for x in note_vels)
                print(f'     # amp "{vels_str}"')

            if legatos is not None:
                note_legatos = [x for x in legatos[:, 0]]
                if _args.consolidate:
                    note_legatos = simplify_repeats(note_legatos)
                legatos_str = " ".join(str(x) for x in note_legatos)
                print(f'     # legato "{legatos_str}"')
        else:
            # Multi-voice track - use stack
            print(f"  d{i + 1} $ {slow_cmd}stack [")
            for j in range(n_voices):
                notes_names = [midinote_to_note_name(x) for x in notes[:, j]]
                if _args.consolidate:
                    notes_names = simplify_repeats(notes_names)
                notes_str = " ".join(str(x) for x in notes_names)

                comma = "," if j < n_voices - 1 else ""

                if vels is not None or legatos is not None:
                    print(f'       n "{notes_str}"')
                    if vels is not None:
                        note_vels = [vel_to_amp(x) for x in vels[:, j]]
                        if _args.consolidate:
                            note_vels = simplify_repeats(note_vels)
                        vels_str = " ".join(str(x) for x in note_vels)
                        print(f'       # amp "{vels_str}"')
                    if legatos is not None:
                        note_legatos = [x for x in legatos[:, j]]
                        if _args.consolidate:
                            note_legatos = simplify_repeats(note_legatos)
                        legatos_str = " ".join(str(x) for x in note_legatos)
                        print(f'       # legato "{legatos_str}"{comma}')
                else:
                    print(f'       n "{notes_str}"{comma}')
            print("     ]")

        # Add sound and effects
        print(f'     # s "superpiano"')
        print(f"     # sustain 0.5")
        print(f"     # gain 0.8")
        pan_val = 0.3 + (i * 0.2) if i < 4 else 0.5
        print(f"     # pan {pan_val}")

    print("")
    print("hush")


def print_strudel(_args, notes, vels, legatos, strudel_indent="\n  "):
    n_voices = notes.shape[1]
    # print(n_voices)
    if n_voices == 1:
        print_strudel_notes(_args, notes, strudel_indent)
        print_strudel_vels(_args, vels[:, 0], strudel_indent)
        print_strudel_legatos(_args, legatos[:, 0], strudel_indent)
    elif n_voices > 1:
        print(f"stack(", end="")
        for v in range(n_voices):
            print_strudel_notes(_args, notes[:, v], strudel_indent)
            print_strudel_vels(_args, vels[:, v], strudel_indent)
            print_strudel_legatos(_args, legatos[:, v], strudel_indent)
            print(",", end="")
        # closing the stack
        print("\n)", end="")
    # fix tempo
    if n_voices > 1:
        slow_cmd = f".slow({notes.shape[0] / _args.resolution}/4)"
    else:
        slow_cmd = f"\n.slow({notes.shape[0] / _args.resolution}/4)"
    print(slow_cmd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("midi_files", nargs="*")
    parser.add_argument(
        "--events",
        "-e",
        const=True,
        default=False,
        help="print midi event information",
        action="store_const",
    )
    parser.add_argument(
        "--debug",
        "-d",
        const=True,
        default=False,
        help="print midi event information, voice numbers, and quanta numbers for debugging",
        action="store_const",
    )
    parser.add_argument(
        "--shape",
        "-p",
        const=True,
        default=False,
        help="print midi shape",
        action="store_const",
    )
    parser.add_argument(
        "--resolution",
        "-q",
        default=4,
        type=int,
        help="specify number of quanta per quarter note",
    )
    parser.add_argument(
        "--legato",
        "-l",
        const=True,
        default=False,
        help="print legato pattern",
        action="store_const",
    )
    parser.add_argument(
        "--amp",
        "-a",
        const=True,
        default=False,
        help="print amplitude pattern",
        action="store_const",
    )
    parser.add_argument(
        "--consolidate",
        "-c",
        const=True,
        default=False,
        help="consolidate repeated notes and values with '!' notation",
        action="store_const",
    )
    parser.add_argument(
        "--name", "-n", default="", type=str, help="make a variable and name it"
    )
    parser.add_argument(
        "--brackets",
        "-b",
        const=True,
        default=False,
        help="add :} and {: brackets before and after",
        action="store_const",
    )
    parser.add_argument(
        "--scale",
        "-s",
        const=True,
        default=False,
        help="prints notes in a scale",
        action="store_const",
    )
    parser.add_argument(
        "--strudel",
        "-j",
        const=True,
        default=False,
        help="prints strudel code",
        action="store_const",
    )
    parser.add_argument(
        "--hide",
        "-H",
        const=True,
        default=False,
        help="hide printing name of midi file and inferred polyphony",
        action="store_const",
    )
    parser.add_argument(
        "--singletrack",
        "-1",
        const=True,
        default=False,
        help="process only last track (original behavior, for single-track MIDI)",
        action="store_const",
    )
    args = parser.parse_args()
    for midi_file in args.midi_files:
        if not args.hide:
            print(midi_file)

        # Use multitrack mode by default, singletrack if requested
        if not args.singletrack:
            tracks_data, n_quanta = midi_to_multitrack_arrays(
                midi_file,
                quanta_per_qn=args.resolution,
                velocity_on=args.amp,
                legato_on=args.legato,
                print_events=args.events,
                debug=args.debug,
                hide=args.hide,
            )
            if args.shape:
                print(f"quanta: {n_quanta}")
                print(f"tracks: {len(tracks_data)}")
                for t in tracks_data:
                    print(f"  {t['name']}: {t['polyphony']} voices")
            print_tidal_multitrack(args, tracks_data, n_quanta)
        else:
            # Original single-track behavior
            data = midi_to_array(
                midi_file,
                quanta_per_qn=args.resolution,
                velocity_on=args.amp,
                legato_on=args.legato,
                print_events=args.events,
                debug=args.debug,
                hide=args.hide,
            )
            vels = None
            legatos = None
            consolidate = None
            if args.amp:
                if args.legato:
                    notes, vels, legatos = data
                else:
                    notes, vels = data
            elif args.legato:
                notes, legatos = data
            else:
                notes = data
            if args.shape:
                print("quanta: ", end="")
                print(notes.shape[0])
                print("voices: ", end="")
                print(notes.shape[1])
            if not args.strudel:
                print_tidal(args, notes, vels, legatos)
            else:
                print_strudel(args, notes, vels, legatos)
