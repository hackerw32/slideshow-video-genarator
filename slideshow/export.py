"""The whole ffmpeg export pipeline: clips, transitions, watermark, music."""

import io
import json
import os
import random
import re
import subprocess
import tempfile
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog

from .deps import (Image, ImageTk, ImageFilter, ImageDraw, ImageFont, ImageEnhance,
                   VideoFileClip, AudioFileClip, concatenate_audioclips, np,
                   DND_FILES, TkinterDnD, TKDND_AVAILABLE)


class ExportMixin:
    """The whole ffmpeg export pipeline: clips, transitions, watermark, music."""

    def export_video(self):
        n = self.name_var.get().strip()
        if not n:
            messagebox.showwarning(
                "Λείπει το όνομα",
                "Παρακαλώ γράψε ένα όνομα για το project πριν κάνεις Generate Video!"
            )
            return
        out = Path(self.out_var.get()) / f"{n}.mp4"
        self._export_cancel = False
        if getattr(self, "cancel_btn", None) is not None:
            self.cancel_btn.config(state='normal')
        self.status.config(text="Exporting...")
        threading.Thread(target=self._export_task, args=(out,), daemon=True).start()


    def cancel_export(self):
        """Ask the running export to stop (kills the current ffmpeg too)."""
        self._export_cancel = True
        self.status.config(text="Ακύρωση...")
        proc = self._export_proc
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass


    def _export_task(self, out_path):
        try:
            temp_dir = self.app_dir / "temp"
            temp_dir.mkdir(exist_ok=True)
            for f in temp_dir.glob("*"):
                try: f.unlink()
                except: pass

            res = self.settings["resolution"]
            width, height = map(int, res.split('x'))
            image_duration = self.settings.get("slide_duration", 3)
            cpu_count = os.cpu_count() or 8

            # Fresh debug log for this export run
            try:
                (temp_dir / "export_log.txt").unlink()
            except OSError:
                pass
            self._log_export(f"EXPORT START: {len(self.media_files)} items, res={res}, "
                             f"bg={self.settings.get('background_mode')}, "
                             f"slide_dur={image_duration}s, "
                             f"music_folder={self.settings.get('music_folder')}")
            self._export_music_missing = False
            self._export_voice_used = False

            clip_files = []
            clip_durations = []
            total_duration = 0
            audio_specs = []   # videos whose own sound must be kept (with trim + position)

            for i, (m_type, path, edit) in enumerate(self.media_files):
                if self._export_cancel:
                    raise RuntimeError("cancelled")
                self.progress_var.set((i / len(self.media_files)) * 50)
                clip_path = temp_dir / f"clip_{i:04d}.mp4"
                segs = None

                if m_type == "image":
                    img = Image.open(path)
                    img = self._apply_image_edit(img, edit, path, m_type="image")
                    img = self._fit_image_logic(img, width, height, m_type)
                    fit_move_data = getattr(img, 'fit_move_data', None)
                    if fit_move_data is None:
                        png_path = temp_dir / f"frame_{i:04d}.png"
                        img = self.render_text_on_image(img, self.get_text_for("image"), width, height)
                        img.save(str(png_path), "PNG")

                        cmd = ['ffmpeg', '-y', '-loop', '1', '-i', str(png_path), '-t', str(image_duration),
                               '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-r', '30',
                               '-pix_fmt', 'yuv420p', '-an', str(clip_path)]
                        self._run_ffmpeg_or_raise(cmd, f"encoding image clip {i}")
                        clip_dur = float(image_duration)
                    else:
                        clip_dur = self._render_fit_and_move_clip(
                            img, fit_move_data, temp_dir, i, width, height, image_duration, clip_path
                        )
                else:
                    v = VideoFileClip(path)
                    full_dur = v.duration
                    v.close()

                    # Trim: non-destructive. One kept range keeps using the
                    # classic input-seek fast path; several ranges (the
                    # multi-cut timeline) are trimmed and joined here instead.
                    segs = self.video_keep_segments(edit, full_dur)
                    dur = sum(d for _, d in segs)
                    first_start = segs[0][0]
                    trim_prefix = self.video_trim_filter(segs)
                    self._log_export(f"item {i} video trim: {len(segs)} segment(s) "
                                     f"{[(round(s, 2), round(d, 2)) for s, d in segs]}, "
                                     f"total {dur:.2f}s")

                    txt_overlay = Image.new("RGBA", (width, height), (0,0,0,0))
                    txt_overlay = self.render_text_on_image(txt_overlay, self.get_text_for("video"), width, height)
                    txt_p = temp_dir / f"txt_{i:04d}.png"
                    txt_overlay.save(str(txt_p), "PNG")

                    bg_p = temp_dir / f"bg_{i:04d}.png"
                    first_f = self._apply_image_edit(self._video_first_frame(path), edit, m_type="video")
                    self._create_blur_bg(first_f, width, height).save(str(bg_p), "PNG")

                    # Crop first (fractions of the source), then the usual fit.
                    crop_part = self.video_crop_filter(edit)
                    color_part = self.video_color_filter(edit)

                    if self.settings["cropping"]:
                        vf = crop_part + f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
                    else:
                        vf = crop_part + f"scale={width}:{height}:force_original_aspect_ratio=decrease"
                    if color_part:
                        vf += "," + color_part

                    in_args = (['-ss', f"{first_start:.3f}", '-i', str(path)] if first_start > 0.005
                               else ['-i', str(path)])
                    cmd = (['ffmpeg', '-y'] + in_args +
                           ['-loop', '1', '-i', str(bg_p),
                            '-loop', '1', '-i', str(txt_p),
                            '-filter_complex',
                            f'{trim_prefix}{vf},format=yuv420p[v];'
                            f'[1:v][v]overlay=(W-w)/2:(H-h)/2[base];[base][2:v]overlay=0:0',
                            '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-r', '30', '-pix_fmt', 'yuv420p',
                            '-t', str(dur), '-an', str(clip_path)])
                    self._run_ffmpeg_or_raise(cmd, f"encoding video clip {i}")
                    clip_dur = float(dur)

                    # The first frame of a video clip renders only the blurred background.
                    # Skip it so playback starts from the second frame.
                    if m_type == "video" and not clip_files and clip_path.exists():
                        trimmed_path = temp_dir / f"clip_{i:04d}_t.mp4"
                        r = subprocess.run(['ffmpeg', '-y', '-i', str(clip_path),
                                            '-vf', "select='gte(n,1)',setpts=PTS-STARTPTS",
                                            '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                                            '-r', '30', '-pix_fmt', 'yuv420p', '-an',
                                            str(trimmed_path)], capture_output=True)
                        if r.returncode == 0 and trimmed_path.exists():
                            clip_path.unlink()
                            trimmed_path.rename(clip_path)
                            clip_dur -= 1 / 30
                        else:
                            # A failed trim can leave a partial file - never use it.
                            if trimmed_path.exists():
                                try:
                                    trimmed_path.unlink()
                                except OSError:
                                    pass
                            self._log_export(f"item {i}: first-frame trim failed, keeping original clip")

                if clip_path.exists():
                    clip_files.append(clip_path)
                    clip_durations.append(clip_dur)
                    total_duration += clip_dur
                    # Remember where this clip sits (clip index) and its kept
                    # ranges, so its own sound can be aligned to the merged video.
                    if m_type == "video" and segs and self._video_audio_enabled(edit):
                        audio_specs.append({"path": path, "segs": segs,
                                            "pos": len(clip_files) - 1})

                self._log_export(f"item {i} [{m_type}] {Path(path).name[:50]}: "
                                 f"clip={'OK' if clip_path.exists() else 'MISSING'} "
                                 f"dur={clip_dur:.2f}s")

            # Merge clips with transitions
            self.progress_var.set(60)
            merged = temp_dir / "merged.mp4"
            self._build_merged_with_transitions(clip_files, clip_durations, temp_dir, merged)
            self._log_export(f"merge: {len(clip_files)} clips, total {total_duration:.1f}s, "
                             f"merged={'OK' if merged.exists() else 'FAILED'}")

            # Apply watermark
            self.progress_var.set(75)
            merged_wm = temp_dir / "merged_wm.mp4"
            self._apply_watermark(merged, merged_wm, width, height, temp_dir)

            # Add Music - use the ACTUAL merged video length (not the raw sum of
            # clips, which is a bit longer because transitions overlap).
            probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                    '-of', 'default=noprint_wrappers=1:nokey=1', str(merged_wm)],
                                   capture_output=True, text=True)
            try:
                video_dur = float(probe.stdout.strip())
            except:
                # Estimate the merged length from the raw sum of clips, minus the
                # time consumed by xfade transition overlaps. A plain concat
                # (effect "none" or a single clip) has no overlap at all.
                if self.settings.get("transition_effect") != "none" and len(clip_files) > 1:
                    overlaps = (len(clip_files) - 1) * float(self.settings.get("transition_duration", 0.7))
                    video_dur = max(1.0, float(total_duration) - overlaps)
                else:
                    video_dur = max(1.0, float(total_duration))
            self._log_export(f"video duration for music: {video_dur:.1f}s "
                             f"(sum of clips={total_duration:.1f}s)")
            voice_path = self._build_video_audio_track(audio_specs, clip_durations,
                                                       video_dur, temp_dir)
            self.finalize_audio_ffmpeg(merged_wm, out_path, video_dur, temp_dir, voice_path)
            self.progress_var.set(100)
            if getattr(self, '_export_music_missing', False):
                if getattr(self, '_export_voice_used', False):
                    note = "\n\nΣημείωση: δεν βρέθηκε μουσική — ακούγεται μόνο ο ήχος των βίντεο."
                else:
                    note = "\n\nΣημείωση: δεν βρέθηκε μουσική, το βίντεο είναι χωρίς ήχο."
            else:
                note = ""
            self.root.after(0, lambda: messagebox.showinfo("Done", "Export Complete!" + note))
        except Exception as e:
            self._log_export(f"EXPORT ERROR: {e}")
            if self._export_cancel:
                self._log_export("EXPORT CANCELLED by user")
                self.root.after(0, lambda: messagebox.showinfo(
                    "Export", "Η εξαγωγή ακυρώθηκε."))
            else:
                self._log_export(traceback.format_exc())
                # Bind the text now: Python clears the `except ... as e` name when
                # the block ends, so a lambda captured over `e` would fail later.
                err_msg = str(e)
                self.root.after(0, lambda: messagebox.showerror("Error", err_msg))
        finally:
            self._export_cancel = False
            self._export_proc = None
            if getattr(self, "cancel_btn", None) is not None:
                self.root.after(0, lambda: self.cancel_btn.config(state='disabled'))
            self.root.after(0, lambda: self.status.config(text="Ready"))


    def _log_export(self, msg):
        """Append a debug line to temp/export_log.txt (shows the latest export)."""
        try:
            log = self.app_dir / "temp" / "export_log.txt"
            with open(log, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
        except Exception:
            pass


    def _run_ffmpeg_or_raise(self, cmd, what):
        """Run ffmpeg, polling so the user can cancel, and surface failures.

        stdout is discarded and stderr is captured to a temp file (instead of a
        pipe) so a chatty ffmpeg can never deadlock on a full pipe.
        """
        err_file = tempfile.TemporaryFile()
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=err_file)
        self._export_proc = proc
        try:
            while proc.poll() is None:
                if self._export_cancel:
                    try:
                        proc.terminate()
                        proc.wait(timeout=3)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                    raise RuntimeError("cancelled")
                time.sleep(0.15)
        finally:
            self._export_proc = None
        if proc.returncode != 0:
            try:
                err_file.seek(0)
                err = err_file.read().decode(errors='replace')[-500:]
            except Exception:
                err = ""
            err_file.close()
            self._log_export(f"ffmpeg FAILED {what}: {err}")
            raise RuntimeError(f"ffmpeg failed while {what}:\n{err}")
        err_file.close()
        return proc


    def _clip_offsets(self, durations, effect, transition_duration):
        """Start time of each clip in the merged timeline (matches the merge)."""
        offsets = [0.0]
        cum = 0.0
        for i in range(1, len(durations)):
            cum += durations[i - 1]
            if effect == "none":
                offsets.append(cum)
            else:
                offsets.append(max(0.0, cum - i * transition_duration))
        return offsets


    def _build_video_audio_track(self, specs, clip_durations, total_dur, temp_dir):
        """One AAC track with the original sound of every unmuted video.

        Each video's kept ranges are trimmed exactly like the video export and
        delayed to the moment its clip starts in the merged timeline, so the
        sound stays in sync even with transitions. Returns None when no video
        has usable sound.
        """
        if not specs:
            return None
        effect = self.settings.get("transition_effect", "fade")
        td = float(self.settings.get("transition_duration", 0.7) or 0.7)
        offsets = self._clip_offsets(clip_durations, effect, td)

        inputs, graph, ends = [], [], []
        for spec in specs:
            if not self._video_has_audio(spec["path"]):
                self._log_export(f"audio: skipped {Path(spec['path']).name} (no audio stream)")
                continue
            j = len(inputs) // 2
            inputs += ['-i', str(spec["path"])]
            segs = spec["segs"] or []
            chain = "aresample=44100,aformat=channel_layouts=stereo"
            if len(segs) == 1:
                s, d = segs[0]
                graph.append(f"[{j}:a]atrim=start={s:.3f}:duration={d:.3f},asetpts=PTS-STARTPTS,{chain}[va{j}]")
            else:
                for m, (s, d) in enumerate(segs):
                    graph.append(f"[{j}:a]atrim=start={s:.3f}:duration={d:.3f},asetpts=PTS-STARTPTS[va{j}_{m}]")
                graph.append("".join(f"[va{j}_{m}]" for m in range(len(segs))) +
                             f"concat=n={len(segs)}:v=0:a=1[vc{j}]")
                graph.append(f"[vc{j}]{chain}[va{j}]")
            off_ms = int(round(offsets[spec["pos"]] * 1000))
            if off_ms > 0:
                graph.append(f"[va{j}]adelay={off_ms}:all=1[p{j}]")
                ends.append(f"[p{j}]")
            else:
                ends.append(f"[va{j}]")

        if not ends:
            return None
        if len(ends) == 1:
            graph.append(f"{ends[0]}apad[voice]")
        else:
            graph.append("".join(ends) +
                         f"amix=inputs={len(ends)}:normalize=0:duration=longest,apad[voice]")

        voice = temp_dir / "video_audio.m4a"
        cmd = (['ffmpeg', '-y'] + inputs +
               ['-filter_complex', ";".join(graph), '-map', '[voice]',
                '-c:a', 'aac', '-t', f"{max(0.1, float(total_dur)):.3f}", str(voice)])
        self._run_ffmpeg_or_raise(cmd, "building the video audio track")
        self._log_export(f"audio: mixed {len(ends)} video sound track(s) -> {voice.name}")
        return voice


    def _probe_duration(self, path, default=1.0):
        """Duration of a media file in seconds (ffprobe), or ``default``."""
        try:
            r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
                               capture_output=True, text=True)
            d = float(r.stdout.strip())
            return d if d > 0 else default
        except Exception:
            return default


    def _prepared_music(self, path, temp_dir, index):
        """A copy of a music track with leading/trailing silence removed.

        Returns (path, duration). On any failure the original is returned so the
        export still runs. The trimmed copy is cached in temp for this run.
        """
        out = temp_dir / f"music_trim_{index:02d}.m4a"
        sr = "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05:detection=peak"
        af = (sr + ",areverse," + sr + ",areverse," +
              "aresample=44100,aformat=channel_layouts=stereo")
        try:
            self._run_ffmpeg_or_raise(['ffmpeg', '-y', '-i', str(path), '-af', af,
                                       '-c:a', 'aac', str(out)], "trimming music silence")
        except Exception as e:
            self._log_export(f"music: trim failed for {Path(path).name} ({e}); using original")
            return path, self._probe_duration(path)
        return out, self._probe_duration(out)


    def finalize_audio_ffmpeg(self, vid_p, out_p, duration, temp_dir, voice_path=None):
        cf = max(0.0, float(self.settings.get("crossfade_duration", 0) or 0))
        trim = bool(self.settings.get("trim_silence", False))
        vol = 10**(self.settings["volume_db"] / 20)
        vg = 10**(float(self.settings.get("video_audio_volume_db", 0) or 0) / 20)

        tracks = []      # original music files (for the used-music tracker/logs)
        raw_durs = []
        rem = duration
        guard = 0
        while rem > 0:
            guard += 1
            if guard > 300:  # safety cap - never loop forever
                self._log_export("music: safety cap reached, stopping selection")
                break
            m = self.get_next_music()
            if not m:
                break
            if not Path(m).exists():
                # The file was deleted but is still listed in the tracker.
                self.mark_music_used(m)
                self._log_export(f"music: skipped missing file {Path(m).name}")
                continue
            tracks.append(m)
            self.mark_music_used(m)  # advances the rotation in memory
            d = self._probe_duration(m)
            raw_durs.append(d)
            self._log_export(f"music: +{Path(m).name} ({d:.1f}s)")
            rem -= d

        # Optional silence-trim first, so the bed we measure uses real durations.
        bed, bed_durs = [], []
        for k, m in enumerate(tracks):
            p, d = self._prepared_music(m, temp_dir, k) if trim else (m, raw_durs[k])
            bed.append(p)
            bed_durs.append(d)

        def coverage():
            # Crossfades shorten the bed by (n-1)*cf.
            return sum(bed_durs) - max(0, len(bed) - 1) * cf

        # Keep adding tracks until the bed really covers the video.
        while bed and coverage() < duration and guard < 300:
            guard += 1
            m = self.get_next_music()
            if not m or not Path(m).exists():
                break
            tracks.append(m)
            self.mark_music_used(m)
            p, d = (self._prepared_music(m, temp_dir, len(tracks) - 1) if trim
                    else (m, self._probe_duration(m)))
            bed.append(p)
            bed_durs.append(d)
            self._log_export(f"music: +{Path(m).name} ({d:.1f}s) for crossfade/trim coverage")

        self._log_export(f"music: {len(tracks)} track(s), bed {sum(bed_durs):.1f}s "
                         f"(video {duration:.1f}s, crossfade={cf:.1f}s, trim_silence={trim})")

        if not tracks:
            # No music available. Keep the video's own sound if enabled,
            # otherwise just copy the silent video (instead of erroring).
            self._export_music_missing = True
            use_voice = bool(voice_path and Path(voice_path).exists())
            tmp_out = out_p.with_name(out_p.stem + "_tmp" + out_p.suffix)
            try:
                if use_voice:
                    self._run_ffmpeg_or_raise(
                        ['ffmpeg', '-y', '-i', str(vid_p), '-i', str(voice_path),
                         '-map', '0:v', '-filter:a', f'volume={vg:.4f}',
                         '-c:v', 'copy', '-c:a', 'aac',
                         '-shortest', str(tmp_out)], "adding video sound (no music)")
                else:
                    self._run_ffmpeg_or_raise(['ffmpeg', '-y', '-i', str(vid_p), '-c', 'copy', str(tmp_out)],
                                              "copying video")
                os.replace(tmp_out, out_p)
            finally:
                try:
                    tmp_out.unlink()
                except OSError:
                    pass
            self._export_voice_used = use_voice
            self._log_export("music: none found, video kept " +
                             ("with its own audio" if use_voice else "without audio"))
            return

        if coverage() < duration - 0.1:
            raise RuntimeError(
                f"Η μουσική που επιλέχθηκε είναι μόνο ~{coverage():.0f} δευτ., ενώ το βίντεο θέλει "
                f"{duration:.0f} δευτ. Πρόσθεσε περισσότερα τραγούδια στον φάκελο μουσικής "
                "ή κάνε Refresh Music List στις ρυθμίσεις."
            )

        # Keep a crossfade shorter than the shortest track.
        if len(bed) > 1 and cf > 0:
            cf = min(cf, max(0.1, min(bed_durs) - 0.1))

        # ---- build the music filter graph (crossfade / concat / volume) ----
        inputs = ['-i', str(vid_p)]
        for p in bed:
            inputs += ['-i', str(p)]
        pre, labels = [], []
        for k in range(len(bed)):
            pre.append(f"[{k + 1}:a]aresample=44100,aformat=channel_layouts=stereo[m{k}]")
            labels.append(f"[m{k}]")

        if len(bed) == 1:
            mcat = labels[0]
        elif cf > 0:
            cur = labels[0]
            for k in range(1, len(bed)):
                out = f"[c{k}]" if k < len(bed) - 1 else "[mcat]"
                pre.append(f"{cur}{labels[k]}acrossfade=d={cf:.3f}:c1=tri:c2=tri{out}")
                cur = out
            mcat = "[mcat]"
        else:
            pre.append("".join(labels) + f"concat=n={len(bed)}:v=0:a=1[mcat]")
            mcat = "[mcat]"

        # Mix the (optional) original video sound under the music. Duration is
        # taken from the music (>= the video), then -shortest trims to the video.
        use_voice = bool(voice_path and Path(voice_path).exists())
        if use_voice:
            voice_idx = 1 + len(bed)
            inputs += ['-i', str(voice_path)]
            pre.append(f"{mcat}volume={vol:.4f}[music]")
            pre.append(f"[{voice_idx}:a]volume={vg:.4f}[voice]")
            pre.append("[music][voice]amix=inputs=2:duration=first:normalize=0[a]")
        else:
            pre.append(f"{mcat}volume={vol:.4f}[a]")

        cmd = (['ffmpeg', '-y'] + inputs +
               ['-filter_complex', ";".join(pre), '-map', '0:v', '-map', '[a]',
                '-c:v', 'copy', '-c:a', 'aac', '-shortest', str(out_p)])
        self._export_voice_used = use_voice

        # Mux to a temporary file (same dir, valid .mp4 extension so ffmpeg can
        # infer the format) and verify before replacing the destination, so a
        # failed/truncated export never destroys the user's previous output file.
        tmp_out = out_p.with_name(out_p.stem + "_tmp" + out_p.suffix)
        cmd[cmd.index(str(out_p))] = str(tmp_out)
        try:
            self._run_ffmpeg_or_raise(cmd, "mixing music into video")

            # Final safety net: -shortest can truncate the video if the music turned
            # out shorter than expected. Verify the whole video is kept.
            out_dur = self._probe_duration(tmp_out, default=0.0)
            self._log_export(f"music: final output {out_dur:.1f}s (video was {duration:.1f}s)")
            if out_dur < duration - 0.1:
                raise RuntimeError(
                    f"Το τελικό βίντεο βγήκε μόνο {out_dur:.0f} δευτ. ενώ έπρεπε να είναι {duration:.0f} δευτ. "
                    "Μάλλον η μουσική ήταν πιο σύντομη από το βίντεο. Πρόσθεσε περισσότερα τραγούδια "
                    "στον φάκελο μουσικής ή κάνε Refresh Music List στις ρυθμίσεις."
                )
            os.replace(tmp_out, out_p)
        finally:
            try:
                tmp_out.unlink()
            except OSError:
                pass

        # Only now that the output succeeded, persist the used-music marks - so a
        # failed export doesn't burn the music for the next attempt.
        for m in tracks:
            self.mark_music_used(m)
        self.save_music_tracker()
        self._log_export(f"music: output written ({Path(out_p).name}), {len(tracks)} track(s) marked used")


    def _build_merged_with_transitions(self, clip_files, clip_durations, temp_dir, merged):
        """Merge clip files using xfade transitions (or simple concat if effect is 'none')."""
        effect = self.settings.get("transition_effect", "fade")
        td = self.settings.get("transition_duration", 0.7)
        XFADE_EFFECTS = ["fade", "fadeblack", "fadewhite", "wipeleft", "wiperight",
                         "wipeup", "wipedown", "smoothleft", "smoothright"]

        if effect == "none" or len(clip_files) <= 1:
            concat_file = temp_dir / "list.txt"
            with open(concat_file, 'w', encoding='utf-8') as f:
                for c in clip_files:
                    f.write(f"file '{str(c).replace(os.sep, '/')}'\n")
            self._run_ffmpeg_or_raise(['ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                                       '-i', str(concat_file), '-c', 'copy', str(merged)],
                                      "merging clips (concat)")
            return

        inputs = []
        for c in clip_files:
            inputs += ['-i', str(c)]

        n = len(clip_files)
        filter_parts = []
        prev_label = "[0:v]"
        cumulative = 0.0
        for i in range(1, n):
            cumulative += clip_durations[i - 1]
            offset = max(0.0, cumulative - i * td)
            if effect == "random":
                random_pool = self.settings.get("random_transitions", [])
                if not random_pool:
                    random_pool = XFADE_EFFECTS
                eff = random.choice(random_pool)
            else:
                eff = effect
            out_label = f"[x{i}]" if i < n - 1 else ""
            filter_parts.append(
                f"{prev_label}[{i}:v]xfade=transition={eff}:duration={td}:offset={offset:.3f}{out_label}"
            )
            prev_label = f"[x{i}]"

        cmd = (['ffmpeg', '-y'] + inputs +
               ['-filter_complex', ";".join(filter_parts),
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                '-r', '30', '-pix_fmt', 'yuv420p', '-an', str(merged)])
        self._run_ffmpeg_or_raise(cmd, "merging clips with transitions")


    def _effective_image_watermark(self):
        if self.project_watermark.get("enabled") and self.project_watermark.get("path"):
            return self.project_watermark
        if self.settings.get("watermark_enabled") and self.settings.get("watermark_path"):
            return {
                "path": self.settings["watermark_path"],
                "position": self.settings.get("watermark_position", "bottom_right"),
                "size_pct": self.settings.get("watermark_size_pct", 15),
                "opacity": self.settings.get("watermark_opacity", 80),
            }
        return None


    def _effective_text_watermark(self):
        if self.settings.get("watermark_text_enabled") and \
                (self.settings.get("watermark_text") or "").strip():
            return {
                "text": self.settings["watermark_text"].strip(),
                "position": self.settings.get("watermark_text_position", "bottom_left"),
                "size_pct": self.settings.get("watermark_text_size_pct", 6),
                "opacity": self.settings.get("watermark_text_opacity", 90),
                "color": self.settings.get("watermark_text_color", "#ffffff"),
            }
        return None


    def _apply_watermark(self, input_path, output_path, width, height, temp_dir=None):
        """Overlay the image logo and/or the text watermark on the whole video."""
        img_wm = self._effective_image_watermark()
        txt_wm = self._effective_text_watermark()
        has_img = bool(img_wm and Path(img_wm["path"]).exists())

        if not has_img and not txt_wm:
            self._run_ffmpeg_or_raise(['ffmpeg', '-y', '-i', str(input_path), '-c', 'copy', str(output_path)],
                                      "copying video (no watermark)")
            return

        pos_map = {
            "top_left": "10:10",
            "top_right": "W-w-10:10",
            "bottom_left": "10:H-h-10",
            "bottom_right": "W-w-10:H-h-10",
            "center": "(W-w)/2:(H-h)/2"
        }
        inputs = ['-i', str(input_path)]
        fc = []
        base = "[0:v]"
        idx = 1
        if has_img:
            wm_w = max(2, int(width * img_wm["size_pct"] / 100))
            alpha = img_wm["opacity"] / 100.0
            inputs += ['-i', img_wm["path"]]
            fc.append(f"[{idx}:v]scale={wm_w}:-1,format=rgba,"
                      f"colorchannelmixer=aa={alpha:.2f}[wm{idx}]")
            xy = pos_map.get(img_wm["position"], "W-w-10:H-h-10")
            fc.append(f"{base}[wm{idx}]overlay={xy}[v{idx}]")
            base = f"[v{idx}]"
            idx += 1
        if txt_wm:
            font_size = max(8, int(height * txt_wm["size_pct"] / 100))
            timg = self._watermark_text_image(txt_wm["text"], txt_wm["color"], font_size,
                                              txt_wm["opacity"] / 100.0)
            tp = (temp_dir or self.temp_dir) / "wm_text.png"
            timg.save(str(tp))
            inputs += ['-i', str(tp)]
            fc.append(f"[{idx}:v]format=rgba[wm{idx}]")
            xy = pos_map.get(txt_wm["position"], "10:H-h-10")
            fc.append(f"{base}[wm{idx}]overlay={xy}[v{idx}]")
            base = f"[v{idx}]"
            idx += 1

        cmd = (['ffmpeg', '-y'] + inputs +
               ['-filter_complex', ";".join(fc), '-map', base,
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                '-pix_fmt', 'yuv420p', '-an', str(output_path)])
        self._run_ffmpeg_or_raise(cmd, "applying watermark")

