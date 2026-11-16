"""Revisión LSP local con vista fluida y lectura de fotogramas RGB exactos."""
from __future__ import annotations

import argparse
from collections import OrderedDict
import csv
from fractions import Fraction
from datetime import date, datetime
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import subprocess
import struct
import sys
import threading
from urllib.parse import parse_qs, urlparse
import webbrowser
import xml.etree.ElementTree as ET
import zipfile

APP = Path(__file__).resolve().parent
PROJECT = APP.parent
DATA = APP / 'data'
STATIC = APP / 'dist'
FIELDS = ['resultado', 'revisado_por', 'fecha', 'observacion']
S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
ET.register_namespace('', S)
ET.register_namespace('r', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')


def required(n):
    return n is not None and (1 <= n <= 9 or 50 <= n <= 53 or 104 <= n <= 128)


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def expected(row, effect):
    n = int(row['n']) if row else None
    if n and n <= 4:
        return 'No deben aparecer gafas del simulador. En CUNA_1 y JUNTOS_ORACION_1 se ven sus gafas propias. Si observas eso, elige «coincide».'
    if n and n <= 9:
        return 'Las gafas dibujadas aparecen y desaparecen. Es lo esperado. Comprueba que estén sobre la cara cuando aparecen.'
    if n and 50 <= n <= 53:
        side = 'derecha' if 'derecha' in effect else 'izquierda'
        return f'Debe aparecer un objeto en la mano {side} a ratos (36–47 % del video). Comprueba su posición y seguimiento.'
    if 'blur_' in effect or (row and row['familia'] == 'desenfoque'):
        zone = 'La cara borrosa y el cuerpo sin ese desenfoque' if 'blur_rostro' in effect else 'El cuerpo borroso y la cara nítida' if 'blur_cuerpo' in effect else 'La cara y el cuerpo borrosos'
        return zone + '. Comprueba que el efecto siga el movimiento. Con intensidad 2 o 3 puede ser muy leve. Si no lo percibes, registra «no se nota».'
    if row and row.get('que_mirar'):
        return row['que_mirar']
    return 'Compara el video simulado con el original. Revisa el efecto indicado, su posición y su continuidad. Describe cualquier incidencia.'


def options(record):
    if record['family'] == 'desenfoque' or (record['effect'].startswith('blur_') and ' + ' not in record['effect']):
        return ['correcto', 'caja fija', 'no se nota', 'otro']
    if record['required']:
        return ['coincide', 'no coincide', 'otro']
    return ['correcto', 'no coincide', 'caja fija', 'no se nota', 'otro']


class Catalog:
    def __init__(self, project=PROJECT, csv_path=None, template_path=None):
        self.project = Path(project)
        self.simroot = self.project / 'simulador_escenarios_lsp' / 'salidas'
        self.originalroot = self.project / 'originales_organizados'
        csv_path = Path(csv_path or DATA / 'lista_revision_visual_2026-11-14.csv')
        self.template_path = Path(template_path or DATA / 'plantilla_revision.xlsx')
        self.source = read_csv(csv_path)
        self.headers = list(self.source[0])
        metadata = {r['archivo'].replace('\\', '/').removeprefix('editados/'): r for r in self.source}
        originals = {}
        for split in ('train', 'val', 'test'):
            folder = self.originalroot / f'originales_{split}'
            for p in folder.glob('*/*'):
                if p.suffix.lower() in ('.mp4', '.webm', '.mov', '.avi'):
                    originals.setdefault((split, p.stem), []).append(p)
        self.paths = {}
        self.records = []
        seen = set()
        splits = {'prueba_single_original_sin_perdida': 'test_single', 'editados_train': 'train_edit', 'editados_val': 'val_edit', 'editados_test': 'test_edit'}
        for folder, subset in splits.items():
            root = self.simroot / folder
            runmeta = {}
            if (root / 'resultados.csv').exists():
                for r in read_csv(root / 'resultados.csv'):
                    runmeta[Path(r.get('output', '')).name] = r
            for p in sorted(root.glob('*/*.mp4')):
                if p.parent.name.startswith('_'):
                    continue
                rel = p.relative_to(self.simroot).as_posix()
                row = metadata.get(rel)
                original_name = p.name.split('_clean_', 1)[0]
                if '_clean_' not in p.name:
                    original_name = p.name.split('__', 1)[0]
                effect = p.stem.split('__', 1)[-1]
                info = runmeta.get(p.name, {})
                effect = info.get('preset') or effect
                if effect == 'base' and not row:
                    continue  # Las bases se ofrecen como comparación, no como casos nuevos.
                split = 'test' if subset.startswith('test') else subset.split('_')[0]
                choices = originals.get((split, original_name), [])
                org = next((o for o in choices if o.parent.name == p.parent.name), choices[0] if len(choices) == 1 else None)
                base = p.with_name(p.name.split('__', 1)[0] + '__base.mp4')
                ident = sha256(rel.encode('utf-8')).hexdigest()[:20]
                n = int(row['n']) if row else None
                family = row['familia'] if row else ('desenfoque' if effect.startswith('blur_') else 'gafas' if effect.startswith('gafas_') else 'objeto_mano' if effect.startswith('objeto_mano_') else 'oclusion' if effect.startswith('oclusion_') else 'combinado' if effect.startswith('combinado_') else effect)
                record = {'id': ident, 'n': n, 'required': required(n), 'subset': subset, 'split': split, 'original': row['original'] if row else original_name, 'family': family, 'effect': effect, 'file': rel, 'available': True, 'originalAvailable': org is not None, 'baseAvailable': base.exists(), 'pct': row.get('fotogramas_con_efecto_pct', '') if row else '', 'known': row.get('estado_conocido', '') if row else '', 'warning': row.get('aviso_simulador', '') if row else info.get('message', ''), 'expected': expected(row, effect)}
                record['options'] = options(record)
                self.records.append(record)
                self.paths[ident] = {'simulated': p, 'original': org, 'base': base if base.exists() else None}
                seen.add(rel)
        # Mantener visibles también los casos de la lista cuyo video falte.
        for rel, row in metadata.items():
            if rel in seen:
                continue
            n = int(row['n'])
            ident = sha256(rel.encode()).hexdigest()[:20]
            split = 'test' if row['subconjunto'].startswith('test') else row['subconjunto'].split('_')[0]
            record = {'id': ident, 'n': n, 'required': required(n), 'subset': row['subconjunto'], 'split': split, 'original': row['original'], 'family': row['familia'], 'effect': Path(rel).stem.split('__')[-1], 'file': rel, 'available': False, 'originalAvailable': False, 'baseAvailable': False, 'pct': row['fotogramas_con_efecto_pct'], 'known': row['estado_conocido'], 'warning': row['aviso_simulador'], 'expected': expected(row, rel)}
            record['options'] = options(record)
            self.records.append(record)
            self.paths[ident] = {'simulated': None, 'original': None, 'base': None}
        self.records.sort(key=lambda r: (r['n'] is None, r['n'] or 0, r['file']))
        self.byid = {r['id']: r for r in self.records}
        self.byn = {r['n']: r for r in self.records if r['n'] is not None}
        variants = {}
        for record in self.records:
            variants.setdefault((record['split'], record['original']), []).append(record['id'])
        for record in self.records:
            record['relatedIds'] = variants[(record['split'], record['original'])]
            record['rgbLossless'] = record['subset'] == 'test_single'
            record['beforeAvailable'] = False
        correction = self.simroot/'prueba_single_original_sin_perdida/correcciones_revision_visual_2026-11-15.json'
        if correction.exists():
            journal = json.loads(correction.read_text(encoding='utf-8'))
            for item in journal.get('items', []):
                record = self.byn.get(item['n'])
                backup = Path(item['backup']).resolve()
                if (record and backup.is_relative_to((self.simroot/'_respaldos_revision_visual').resolve())
                        and backup.is_file() and backup.name == Path(record['file']).name):
                    self.paths[record['id']]['before'] = backup
                    record['beforeAvailable'] = True
                    record['correctionDate'] = '2026-11-15'
                    record['detailFocus'] = [[(r['box'][0]+r['box'][2])/2,(r['box'][1]+r['box'][3])/2]
                        for r in item.get('new_record',{}).get('face_regions',[])]
        assert sum(r['required'] for r in self.records) == 38, 'La lista debe contener 38 casos solicitados.'


def mp4_timing(path):
    """Tiempos y muestras de la pista de video, sin decodificarla."""
    with path.open('rb') as f:
        def boxes(start, end):
            pos = start
            while pos + 8 <= end:
                f.seek(pos)
                size, kind = struct.unpack('>I4s', f.read(8))
                header = 8
                if size == 1:
                    size = struct.unpack('>Q', f.read(8))[0]
                    header = 16
                if size == 0:
                    size = end - pos
                if size < header or pos + size > end:
                    break
                yield kind, pos + header, pos + size
                pos += size
        for kind, start, end in boxes(0, path.stat().st_size):
            if kind != b'moov':
                continue
            for kind, ts, te in boxes(start, end):
                if kind != b'trak':
                    continue
                for kind, ms, me in boxes(ts, te):
                    if kind != b'mdia':
                        continue
                    duration, video, frames = None, False, None
                    for kind, ds, de in boxes(ms, me):
                        if kind == b'hdlr':
                            f.seek(ds + 8)
                            video = f.read(4) == b'vide'
                        elif kind == b'mdhd':
                            f.seek(ds)
                            data = f.read(min(40, de - ds))
                            if data[0] == 1:
                                scale, ticks = struct.unpack('>IQ', data[20:32])
                            else:
                                scale, ticks = struct.unpack('>II', data[12:20])
                            duration = ticks / scale
                        elif kind == b'minf':
                            for k, bs, be in boxes(ds, de):
                                if k != b'stbl':
                                    continue
                                for k, ss, se in boxes(bs, be):
                                    if k in (b'stsz', b'stz2'):
                                        f.seek(ss+8)
                                        frames = struct.unpack('>I', f.read(4))[0]
                    if video and duration is not None:
                        if not frames:
                            raise ValueError('No se encontró el conteo de fotogramas.')
                        return dict(duration=duration, frames=frames, fps=frames/duration)
    raise ValueError('No se encontró la duración de la pista de video.')


def mp4_duration(path):
    return mp4_timing(path)['duration']


def webm_with_duration(data, duration):
    """Completar Duration en el WebM de pipe sin desplazar índices ni fotogramas."""
    def vint(pos, ident=False):
        mask, width = 128, 1
        while not data[pos] & mask:
            mask >>= 1
            width += 1
            if width > 8:
                raise ValueError('Cabecera WebM inválida.')
        value = int.from_bytes(data[pos:pos+width], 'big')
        return value if ident else value & ((1 << (7*width)) - 1), width
    def elements(start, end):
        pos = start
        while pos < end:
            ident, iw = vint(pos, True)
            size, sw = vint(pos+iw)
            body = pos+iw+sw
            stop = min(body+size, end)
            yield ident, pos, body, stop
            pos = stop
    for ident, _, segment, end in elements(0, len(data)):
        if ident != 0x18538067:
            continue
        for ident, _, info, stop in elements(segment, end):
            if ident != 0x1549A966:
                continue
            children = list(elements(info, stop))
            scale = next((int.from_bytes(data[b:e], 'big') for i, _, b, e in children if i == 0x2AD7B1), 1000000)
            timing = b'\x44\x89\x88' + struct.pack('>d', duration * 1e9 / scale)
            for ident, start, body, end in children:
                if ident == 0x4489 and end-body == 8:
                    return data[:body] + timing[3:] + data[end:]
                if ident == 0x5741 and end-start >= len(timing)+4:
                    # Acortar solo WritingApp. Su espacio pasa a Duration; los offsets se conservan.
                    app_length = end-start-len(timing)-3
                    if app_length <= 127:
                        writing_app = b'\x57\x41' + bytes([128+app_length]) + b'R'*app_length
                        return data[:start] + timing + writing_app + data[end:]
    raise ValueError('No se pudo completar la duración del WebM compatible.')


class BrowserPlayback:
    """Vista fluida H.264 y fotogramas PNG exactos; cachés separados de las fuentes."""
    VERSION = 'h264-fullhd-crf10-bt709-v2'

    def __init__(self, project=PROJECT, cache_dir=None, ffmpeg=None):
        binaries = Path(project) / 'simulador_escenarios_lsp/.venv/Lib/site-packages/imageio_ffmpeg/binaries'
        self.ffmpeg = ffmpeg or os.environ.get('LSP_FFMPEG') or next(binaries.glob('ffmpeg*.exe'), None) or shutil.which('ffmpeg')
        self.lock = threading.Lock()
        self.cache = OrderedDict()
        self.aliases = OrderedDict()
        self.max_bytes = 120 * 1024 * 1024
        self.cache_dir = Path(cache_dir or Path(project)/'revision_visual_web/data/cache_reproduccion')
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.workers = threading.BoundedSemaphore(2)
        self.key_locks = {}
        self.frames = OrderedDict()

    def file_key(self, path):
        stat = path.stat()
        alias = (str(path), stat.st_mtime_ns, stat.st_size)
        with self.lock:
            key = self.aliases.get(alias)
        if key is None:
            digest = sha256()
            with path.open('rb') as f:
                for block in iter(lambda: f.read(1024*1024), b''):
                    digest.update(block)
            key = digest.hexdigest()
            with self.lock:
                self.aliases[alias] = key
                if len(self.aliases) > 256:
                    self.aliases.popitem(last=False)
        return key

    def run_ffmpeg(self, args, timeout=90):
        if not self.ffmpeg:
            raise ValueError('No se encontró FFmpeg del simulador.')
        with self.workers:
            try:
                result = subprocess.run([str(self.ffmpeg), '-hide_banner', '-loglevel', 'error', '-nostdin',
                    '-threads', '2', *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ValueError('No se pudo preparar la vista del video: '+str(exc)) from exc
        if result.returncode:
            raise ValueError('No se pudo preparar la vista del video: '+result.stderr.decode(errors='replace')[-700:])
        return result.stdout

    def preview(self, path):
        key = sha256((self.VERSION+self.file_key(path)).encode()).hexdigest()
        target = self.cache_dir/(key+'.mp4')
        with self.lock:
            guard = self.key_locks.setdefault(key, threading.Lock())
        with guard:
            if not target.exists():
                temporary = target.with_suffix('.partial.mp4')
                try:
                    timing = mp4_timing(path)
                    rate = str(Fraction(timing['fps']).limit_denominator(1001000))
                    self.run_ffmpeg(['-i', str(path), '-map', '0:v:0', '-an', '-sn',
                        '-vf', 'setpts=PTS-STARTPTS,scale=out_color_matrix=bt709:out_range=tv,format=yuv420p',
                        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '10', '-profile:v', 'high',
                        '-g', '30', '-keyint_min', '30', '-sc_threshold', '0', '-threads', '2',
                        '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709',
                        '-color_range', 'tv', '-r', rate, '-fps_mode', 'cfr', '-map_metadata', '-1',
                        '-movflags', '+faststart', '-y', str(temporary)])
                    actual = mp4_timing(temporary)
                    if (actual['frames'] != timing['frames'] or
                            abs(actual['duration']-timing['duration'])>.001):
                        raise ValueError('La vista previa no conserva todos los fotogramas.')
                    temporary.replace(target)
                finally:
                    temporary.unlink(missing_ok=True)
            target.touch()
        # Solo archivos generados en esta caché. Mantener como máximo 512 MB.
        with self.lock:
            cached = sorted((p for p in self.cache_dir.glob('*.mp4') if re.fullmatch(r'[0-9a-f]{64}\.mp4',p.name)), key=lambda p:p.stat().st_mtime_ns)
            size = sum(p.stat().st_size for p in cached)
            for old in cached:
                if size <= 512*1024*1024:
                    break
                if old != target:
                    try:
                        length = old.stat().st_size
                        old.unlink()
                        size -= length
                    except OSError:
                        pass
        return target

    def frame(self, path, number):
        if not 0 <= number < mp4_timing(path)['frames']:
            raise ValueError('Fotograma fuera del video.')
        key = (self.file_key(path), number)
        with self.lock:
            if key in self.frames:
                self.frames.move_to_end(key)
                return self.frames[key]
        data = self.run_ffmpeg(['-i', str(path), '-map', '0:v:0', '-an', '-sn',
            '-vf', f'select=eq(n\\,{number})', '-frames:v', '1', '-fps_mode', 'passthrough',
            '-c:v', 'png', '-pix_fmt', 'rgb24', '-threads', '1', '-f', 'image2pipe', 'pipe:1'], timeout=45)
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('No se pudo leer el fotograma exacto.')
        with self.lock:
            self.frames[key] = data
            self.frames.move_to_end(key)
            while len(self.frames)>1 and sum(map(len,self.frames.values()))>40*1024*1024:
                self.frames.popitem(last=False)
        return data

    def compatible(self, path):
        stat = path.stat()
        alias = (str(path), stat.st_mtime_ns, stat.st_size)
        with self.lock:
            key = self.aliases.get(alias)
            if key is None:
                digest = sha256()
                with path.open('rb') as f:
                    for block in iter(lambda: f.read(1024*1024), b''):
                        digest.update(block)
                key = digest.hexdigest()
                self.aliases[alias] = key
                if len(self.aliases) > 256:
                    self.aliases.popitem(last=False)
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            if not self.ffmpeg:
                raise ValueError('No se encontró FFmpeg del simulador para reproducir RGB sin pérdida.')
            command = [str(self.ffmpeg), '-hide_banner', '-loglevel', 'error', '-nostdin',
                       '-threads', '2', '-i', str(path), '-map', '0:v:0', '-an', '-sn',
                       '-c:v', 'libvpx-vp9', '-lossless', '1', '-pix_fmt', 'gbrp',
                       '-colorspace', 'rgb', '-color_range', 'pc', '-deadline', 'realtime',
                       '-cpu-used', '8', '-row-mt', '1', '-threads', '2',
                       '-fps_mode', 'passthrough', '-f', 'webm', 'pipe:1']
            try:
                converted = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           timeout=90, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ValueError('No se pudo preparar la reproducción compatible: ' + str(exc))
            if converted.returncode or not converted.stdout:
                raise ValueError('No se pudo decodificar el video RGB: ' + converted.stderr.decode(errors='replace')[-600:])
            data = webm_with_duration(converted.stdout, mp4_duration(path))
            self.cache[key] = data
            while len(self.cache) > 1 and sum(map(len, self.cache.values())) > self.max_bytes:
                self.cache.popitem(last=False)
            return data


class ReviewStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.reviews = {}
        if self.path.exists():
            content = json.loads(self.path.read_text(encoding='utf-8'))
            self.reviews = content.get('reviews', {})

    def snapshot(self):
        with self.lock:
            return {k: dict(v) for k, v in self.reviews.items()}

    def save(self, record, raw):
        if not isinstance(raw, dict):
            raise ValueError('Revisión inválida.')
        review = {k: str(raw.get(k, '')).strip() for k in FIELDS}
        if review['resultado'] not in record['options']:
            raise ValueError('Elige un resultado válido.')
        if not review['revisado_por']:
            raise ValueError('Escribe tu nombre completo.')
        try:
            date.fromisoformat(review['fecha'])
        except ValueError:
            raise ValueError('Escribe una fecha válida en formato AAAA-MM-DD.')
        if len(review['fecha']) != 10:
            raise ValueError('La fecha debe tener formato AAAA-MM-DD.')
        if (review['resultado'] in ('no coincide', 'otro') or raw.get('grave')) and not review['observacion']:
            raise ValueError('Explica qué viste en la observación.')
        if len(review['observacion']) > 5000 or len(review['revisado_por']) > 250:
            raise ValueError('El texto es demasiado largo.')
        review.update(duda=bool(raw.get('duda')), grave=bool(raw.get('grave')), updated_at=datetime.now().astimezone().isoformat(timespec='seconds'))
        if review['duda'] and 'duda' not in review['observacion'].lower():
            review['observacion'] = (review['observacion'] + ' Duda.').strip()
        if review['grave'] and 'grave' not in review['observacion'].lower():
            review['observacion'] = (review['observacion'] + ' Incidencia grave.').strip()
        with self.lock:
            updated = {**self.reviews, record['id']: review}
            payload = json.dumps({'version': 1, 'reviews': updated}, ensure_ascii=False, indent=2)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                self.path.with_suffix('.anterior.json').write_bytes(self.path.read_bytes())
            temp = self.path.with_suffix('.tmp')
            temp.write_text(payload, encoding='utf-8')
            temp.replace(self.path)
            self.reviews = updated
        return review


def export_source(catalog, reviews, official=True):
    rows = []
    for source in catalog.source:
        row = dict(source)
        record = catalog.byn[int(row['n'])]
        review = reviews.get(record['id'])
        if review and (record['required'] or not official):
            for key in FIELDS:
                row[key] = review[key]
        rows.append(row)
    return rows


def csv_bytes(rows, headers):
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=headers, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        # Excel no debe ejecutar texto escrito por el revisor como fórmula.
        writer.writerow({k: ("'" + str(v) if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r')) else v) for k, v in row.items()})
    return out.getvalue().encode('utf-8-sig')


def xlsx_bytes(catalog, reviews):
    template = catalog.template_path
    if not template.exists():
        raise ValueError('No se encontró la plantilla de Excel en data.')
    with zipfile.ZipFile(template) as z:
        content = {n: z.read(n) for n in z.namelist()}
    q = lambda n: '{' + S + '}' + n
    sheet = ET.fromstring(content['xl/worksheets/sheet1.xml'])
    sheetdata = sheet.find(q('sheetData'))
    rowmap = {int(r.attrib['r']): r for r in sheetdata}
    for index, row in enumerate(export_source(catalog, reviews), 2):
        element = rowmap[index]
        for offset, key in enumerate(FIELDS, 10):
            address = chr(65 + offset) + str(index)
            cell = next((c for c in element if c.attrib.get('r') == address), None)
            if cell is None:
                cell = ET.SubElement(element, q('c'), {'r': address})
            for child in list(cell):
                cell.remove(child)
            value = row[key]
            if value == '':
                cell.attrib.pop('t', None)
                continue
            if key == 'fecha':
                cell.attrib.pop('t', None)
                serial = (date.fromisoformat(value) - date(1899, 12, 30)).days
                ET.SubElement(cell, q('v')).text = str(serial)
            else:
                cell.set('t', 'inlineStr')
                text = ET.SubElement(ET.SubElement(cell, q('is')), q('t'))
                text.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
                text.text = value
        element[:] = sorted(element, key=lambda c: (len(re.match('[A-Z]+', c.attrib['r'])[0]), re.match('[A-Z]+', c.attrib['r'])[0]))
    content['xl/worksheets/sheet1.xml'] = ET.tostring(sheet, encoding='utf-8', xml_declaration=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, value in content.items():
            z.writestr(name, value)
    return buffer.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = 'RevisionLSP/2.0'

    def log_message(self, fmt, *args):
        if '/media/' not in self.path and '/frame/' not in self.path:
            super().log_message(fmt, *args)

    def _allowed_host(self):
        host = self.headers.get('Host', '').split(':')[0]
        return host in ('127.0.0.1', 'localhost')

    def send_data(self, data, content_type='application/json; charset=utf-8', status=200, filename=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def json(self, obj, status=200):
        self.send_data(json.dumps(obj, ensure_ascii=False).encode('utf-8'), status=status)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._allowed_host():
            return self.json({'error': 'Solo se admite acceso local.'}, 403)
        parsed = urlparse(self.path)
        route = parsed.path
        cat, store = self.server.catalog, self.server.store
        try:
            if route == '/api/catalog':
                return self.json({'appVersion': 2, 'records': cat.records, 'reviews': store.snapshot(), 'requiredCount': 38, 'sourceCount': len(cat.source), 'paths': {'originals': str(cat.originalroot), 'simulated': str(cat.simroot)}, 'reviewPath': str(store.path)})
            if route == '/api/reviews':
                return self.json({'reviews': store.snapshot()})
            if route.startswith(('/media/', '/frame/', '/timing/')):
                parts = route.strip('/').split('/')
                if len(parts) != 3 or parts[1] not in cat.paths or parts[2] not in ('simulated', 'original', 'base', 'before'):
                    return self.json({'error': 'Video no encontrado.'}, 404)
                path = cat.paths[parts[1]].get(parts[2])
                if not path or not path.is_file():
                    return self.json({'error': 'Video no disponible en la carpeta.'}, 404)
                if parts[0] == 'timing':
                    return self.json(mp4_timing(path))
                if parts[0] == 'frame':
                    value = parse_qs(parsed.query).get('n', ['0'])[0]
                    if not re.fullmatch(r'\d{1,6}', value):
                        raise ValueError('Número de fotograma inválido.')
                    return self.send_data(self.server.playback.frame(path, int(value)), 'image/png')
                if parse_qs(parsed.query).get('vista') == ['fluida']:
                    return self.stream_video(self.server.playback.preview(path), content_type='video/mp4')
                compatible = parse_qs(parsed.query).get('vista') == ['compatible']
                if compatible and cat.byid[parts[1]]['rgbLossless'] and parts[2] != 'original':
                    data = self.server.playback.compatible(path)
                    return self.stream_video(path, data=data, content_type='video/webm')
                return self.stream_video(path)
            if route.startswith('/api/export/'):
                reviews = store.snapshot()
                if route.endswith('/xlsx'):
                    return self.send_data(xlsx_bytes(cat, reviews), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename='lista_revision_visual_2026-11-14_revisada.xlsx')
                if route.endswith('/csv'):
                    return self.send_data(csv_bytes(export_source(cat, reviews), cat.headers), 'text/csv; charset=utf-8', filename='lista_revision_visual_2026-11-14_revisada.csv')
                if route.endswith('/extended'):
                    rows = []
                    for r in cat.records:
                        review = reviews.get(r['id'])
                        if review:
                            rows.append({'n': r['n'] or '', 'subconjunto': r['subset'], 'original': r['original'], 'archivo': r['file'], 'familia': r['family'], **{k: review[k] for k in FIELDS}, 'duda': review['duda'], 'grave': review['grave']})
                    return self.send_data(csv_bytes(rows, ['n', 'subconjunto', 'original', 'archivo', 'familia', *FIELDS, 'duda', 'grave']), 'text/csv; charset=utf-8', filename='revision_ampliada.csv')
                if route.endswith('/json'):
                    return self.send_data(json.dumps({'version': 1, 'reviews': reviews}, ensure_ascii=False, indent=2).encode('utf-8'), filename='respaldo_revision_lsp.json')
                return self.json({'error': 'Formato no disponible.'}, 404)
            files = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js', '/playback.js':'playback.js', '/styles.css': 'styles.css'}
            if route in files:
                p = STATIC / files[route]
                return self.send_data(p.read_bytes(), mimetypes.guess_type(p.name)[0] + '; charset=utf-8')
            return self.json({'error': 'Ruta no encontrada.'}, 404)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except ValueError as e:
            self.json({'error': str(e)}, 400)

    def do_POST(self):
        if not self._allowed_host():
            return self.json({'error': 'Solo se admite acceso local.'}, 403)
        origin = self.headers.get('Origin')
        if origin and urlparse(origin).netloc != self.headers.get('Host'):
            return self.json({'error': 'Origen no autorizado.'}, 403)
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.json({'error': 'Se requiere JSON.'}, 415)
        parts = urlparse(self.path).path.strip('/').split('/')
        if len(parts) != 3 or parts[:2] != ['api', 'reviews'] or parts[2] not in self.server.catalog.byid:
            return self.json({'error': 'Registro no encontrado.'}, 404)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 32768:
                return self.json({'error': 'Tamaño de solicitud inválido.'}, 400)
            data = json.loads(self.rfile.read(size))
            review = self.server.store.save(self.server.catalog.byid[parts[2]], data)
            self.json({'ok': True, 'review': review})
        except (ValueError, TypeError, UnicodeError) as e:
            self.json({'error': str(e)}, 400)

    def stream_video(self, path, data=None, content_type=None):
        size = len(data) if data is not None else path.stat().st_size
        start, end, status = 0, size - 1, 200
        requested = self.headers.get('Range')
        if requested:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
            if not match or not (match[1] or match[2]):
                return self.range_error(size)
            if not match[1]:
                start = max(0, size - int(match[2]))
            else:
                start = int(match[1])
                end = min(int(match[2]), size - 1) if match[2] else size - 1
            if start >= size or end < start or size == 0:
                return self.range_error(size)
            status = 206
        self.send_response(status)
        self.send_header('Content-Type', content_type or mimetypes.guess_type(path.name)[0] or 'video/mp4')
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(end - start + 1))
        if status == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        if self.command == 'HEAD':
            return
        with (io.BytesIO(data) if data is not None else path.open('rb')) as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                block = f.read(min(256 * 1024, remaining))
                if not block:
                    break
                self.wfile.write(block)
                remaining -= len(block)

    def range_error(self, size):
        self.send_response(416)
        self.send_header('Content-Range', f'bytes */{size}')
        self.send_header('Content-Length', '0')
        self.end_headers()


def create_server(port=8765, store_path=None, *, project=PROJECT, csv_path=None, template_path=None, ffmpeg=None):
    catalog = Catalog(project, csv_path, template_path)
    store = ReviewStore(store_path or DATA / 'revisiones.json')
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.catalog, server.store = catalog, store
    server.playback = BrowserPlayback(project=project, cache_dir=DATA/'cache_reproduccion', ffmpeg=ffmpeg)
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--review-file', type=Path, help='Archivo de revisiones alternativo para pruebas locales.')
    parser.add_argument('--project', type=Path, default=PROJECT, help='Carpeta que contiene originales_organizados y simulador_escenarios_lsp.')
    parser.add_argument('--csv', type=Path, help='Lista privada de revisión (UTF-8).')
    parser.add_argument('--template', type=Path, help='Plantilla privada XLSX para exportar.')
    parser.add_argument('--ffmpeg', type=Path, help='Ejecutable FFmpeg con libx264 y libvpx-vp9.')
    args = parser.parse_args()
    try:
        server = create_server(args.port, args.review_file, project=args.project, csv_path=args.csv, template_path=args.template, ffmpeg=args.ffmpeg)
    except (OSError, ValueError, AssertionError) as e:
        print(f'No se pudo iniciar en el puerto {args.port}: {e}', flush=True)
        return 1
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'Revisión visual LSP: {url}\n{len(server.catalog.records)} videos. 38 solicitados. Solo acceso local.\nRevisiones: {server.store.path}', flush=True)
    if args.open:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
