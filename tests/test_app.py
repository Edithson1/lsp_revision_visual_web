import csv
from datetime import date
import io
import os
import json
from pathlib import Path
import tempfile
import struct
import subprocess
from hashlib import sha256
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import zipfile
import server


@unittest.skipUnless(os.environ.get('LSP_INTEGRATION')=='1','Requiere el dataset y los archivos privados; define LSP_INTEGRATION=1.')
class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = server.Catalog()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'reviews.json'
        self.store = server.ReviewStore(self.path)
        self.case = self.catalog.byn[1]

    def tearDown(self):
        self.tmp.cleanup()

    def review(self, **change):
        return dict(resultado='coincide', revisado_por='Revisor de prueba', fecha='2026-11-15', observacion='', **change)

    def test_catalog_required_and_matches_all_sources(self):
        targets = [r for r in self.catalog.records if r['required']]
        self.assertEqual(len(targets), 38)
        self.assertEqual(len(self.catalog.byn), 290)
        self.assertTrue(all(r['available'] and r['originalAvailable'] for r in targets))
        for r in targets:
            self.assertEqual(self.catalog.paths[r['id']]['original'].stem, r['original'])
            self.assertIn('originales_test', self.catalog.paths[r['id']]['original'].parts)
        self.assertTrue(self.catalog.byn[50]['original'].endswith('PEQUEÑA_2'))
        self.assertIn(self.catalog.byn[227]['id'], self.case['relatedIds'])
        self.assertTrue(self.case['rgbLossless'])
        self.assertFalse(self.catalog.byn[227]['rgbLossless'])
        for split in ['train', 'val', 'test']:
            self.assertTrue(any(r['split'] == split for r in self.catalog.records))

    def test_saved_work_survives_restart_and_has_previous_copy(self):
        self.store.save(self.case, self.review())
        self.assertEqual(server.ReviewStore(self.path).snapshot()[self.case['id']]['resultado'], 'coincide')
        changed = self.review()
        changed.update(resultado='otro', observacion='no abre')
        self.store.save(self.case, changed)
        prior = json.loads(self.path.with_suffix('.anterior.json').read_text(encoding='utf-8'))
        self.assertEqual(prior['reviews'][self.case['id']]['resultado'], 'coincide')

    def test_no_result_is_inferred_and_invalid_review_rejected(self):
        for patch in [dict(resultado=''), dict(resultado='otro'), dict(fecha='2026-02-30'), dict(fecha='20261115'), dict(revisado_por='   '), dict(grave=True)]:
            payload = self.review()
            payload.update(patch)
            with self.assertRaises(ValueError): self.store.save(self.case, payload)
        self.assertFalse(self.path.exists())

    def test_official_exports_exclude_optional_review_and_preserve_source(self):
        self.store.save(self.case, self.review())
        optional = next(r for r in self.catalog.records if r['split']=='train' and r['n'])
        payload = self.review()
        payload.update(resultado='correcto')
        self.store.save(optional, payload)
        reviews = self.store.snapshot()
        rows = server.export_source(self.catalog, reviews)
        self.assertEqual(rows[0]['resultado'], 'coincide')
        self.assertEqual(rows[optional['n']-1]['resultado'], '')
        for actual, source in zip(rows, self.catalog.source):
            for key in list(source)[:10]: self.assertEqual(actual[key], source[key])
        with zipfile.ZipFile(io.BytesIO(server.xlsx_bytes(self.catalog, reviews))) as z:
            self.assertIsNone(z.testzip())
            q=lambda n:'{'+server.S+'}'+n
            root=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
            cells={c.attrib['r']:c for c in root.iter(q('c'))}
            self.assertEqual(cells['K2'].find(q('is')).find(q('t')).text,'coincide')
            self.assertIsNone(cells[f"K{optional['n']+1}"].find(q('v')))
            self.assertEqual(int(cells['M2'].find(q('v')).text),(date(2026,11,15)-date(1899,12,30)).days)
            self.assertEqual(len(root.find(q('hyperlinks'))),38)

    def test_text_export_does_not_create_excel_formulas(self):
        body=server.csv_bytes([dict(nombre='=1+1',observacion='Normal')],['nombre','observacion'])
        row=list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'))))[0]
        self.assertEqual(row['nombre'],"'=1+1")


@unittest.skipUnless(os.environ.get('LSP_INTEGRATION')=='1','Requiere el dataset y los archivos privados; define LSP_INTEGRATION=1.')
class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.http=server.create_server(0,Path(cls.tmp.name)/'reviews.json')
        cls.http.playback=server.BrowserPlayback(cache_dir=Path(cls.tmp.name)/'playback')
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True)
        cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.http.server_port}'
        cls.case=cls.http.catalog.byn[1]

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join();cls.tmp.cleanup()

    def test_media_ranges_and_original(self):
        for kind in ['simulated','original','base']:
            with urlopen(Request(self.url+f'/media/{self.case["id"]}/{kind}',headers={'Range':'bytes=0-63'})) as response:
                data=response.read()
                self.assertEqual(response.status,206)
                self.assertEqual(len(data),64)
                self.assertTrue(response.headers['Content-Range'].startswith('bytes 0-63/'))
                self.assertIn(b'ftyp',data)
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.url+f'/media/{self.case["id"]}/simulated',headers={'Range':'bytes=999999999999-'}))
        self.assertEqual(error.exception.code,416)

    def test_compatible_playback_preserves_all_rgb_pixels_and_duration(self):
        path=self.http.catalog.paths[self.case['id']]['simulated']
        before=sha256(path.read_bytes()).hexdigest()
        with urlopen(self.url+f'/media/{self.case["id"]}/simulated?vista=compatible',timeout=90) as response:
            self.assertEqual(response.headers['Content-Type'],'video/webm')
            playback=response.read()
        marker=playback[:1024].find(b'\x44\x89\x88')
        self.assertGreater(marker,0)
        duration=struct.unpack('>d',playback[marker+3:marker+11])[0]/1000
        self.assertAlmostEqual(duration,3.5035,places=6)
        ff=str(self.http.playback.ffmpeg)
        def rgb_hash(input_source, payload=None):
            command=[ff,'-hide_banner','-loglevel','error','-threads','2','-i',input_source,
                     '-map','0:v:0','-an','-pix_fmt','rgb24','-fps_mode','passthrough','-f','hash','-hash','sha256','pipe:1']
            result=subprocess.run(command,input=payload,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,
                                  creationflags=subprocess.CREATE_NO_WINDOW if server.sys.platform=='win32' else 0)
            return result.stdout
        self.assertEqual(rgb_hash(str(path)),rgb_hash('pipe:0',playback))
        self.assertEqual(before,sha256(path.read_bytes()).hexdigest())
        with urlopen(Request(self.url+f'/media/{self.case["id"]}/base?vista=compatible',headers={'Range':'bytes=0-63'})) as response:
            self.assertEqual(response.read(),playback[:64])
        self.assertEqual(len(self.http.playback.cache),1)  # La base idéntica comparte la reproducción.

    def test_mutations_reject_other_origin_and_unknown_media(self):
        body=json.dumps(dict(resultado='coincide',revisado_por='Prueba',fecha='2026-11-15',observacion='')).encode()
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.url+'/api/reviews/'+self.case['id'],data=body,headers={'Content-Type':'application/json','Origin':'http://otro-sitio.invalid'}))
        self.assertEqual(error.exception.code,403)
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url+'/media/../../server.py')
        self.assertEqual(error.exception.code,404)

    def test_fluid_preview_is_full_hd_h264_and_preserves_timing(self):
        case=self.http.catalog.byn[114]
        source=self.http.catalog.paths[case['id']]['simulated']
        original_hash=sha256(source.read_bytes()).hexdigest()
        with urlopen(self.url+f'/media/{case["id"]}/simulated?vista=fluida',timeout=90) as response:
            self.assertEqual(response.headers['Content-Type'],'video/mp4')
            data=response.read()
        path=Path(self.tmp.name)/'preview.mp4';path.write_bytes(data)
        self.assertEqual(server.mp4_timing(path),server.mp4_timing(source))
        self.assertLess(len(data),source.stat().st_size//5)
        info=subprocess.run([str(self.http.playback.ffmpeg),'-hide_banner','-i',str(path)],capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW if server.sys.platform=='win32' else 0).stderr
        self.assertIn(b'h264 (High)',info)
        self.assertIn(b'yuv420p',info)
        self.assertIn(b'1920x1080',info)
        self.assertEqual(original_hash,sha256(source.read_bytes()).hexdigest())
        with urlopen(Request(self.url+f'/media/{case["id"]}/simulated?vista=fluida',headers={'Range':'bytes=0-63'})) as response:
            self.assertEqual(response.status,206)
            self.assertEqual(response.read(),data[:64])

    def test_exact_frame_matches_source_rgb_and_before_is_available(self):
        case=self.http.catalog.byn[114]
        self.assertTrue(case['beforeAvailable'])
        source=self.http.catalog.paths[case['id']]['simulated']
        with urlopen(self.url+f'/frame/{case["id"]}/simulated?n=51',timeout=45) as response:
            self.assertEqual(response.headers['Content-Type'],'image/png')
            png=response.read()
        ff=str(self.http.playback.ffmpeg)
        def digest(args,payload=None):
            result=subprocess.run([ff,'-v','error','-threads','2',*args,'-an','-pix_fmt','rgb24',
                '-f','hash','-hash','sha256','pipe:1'],input=payload,capture_output=True,check=True,
                creationflags=subprocess.CREATE_NO_WINDOW if server.sys.platform=='win32' else 0)
            return result.stdout
        self.assertEqual(digest(['-i',str(source),'-vf','select=eq(n\\,51)','-frames:v','1']),digest(['-i','pipe:0'],png))
        for kind in ('before','base','simulated'):
            with urlopen(self.url+f'/timing/{case["id"]}/{kind}') as response:
                self.assertEqual(json.load(response)['frames'],142)
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url+f'/frame/{case["id"]}/simulated?n=999999')
        self.assertEqual(error.exception.code,400)

    def test_save_reopen_and_export_via_http(self):
        body=json.dumps(dict(resultado='coincide',revisado_por='Prueba HTTP',fecha='2026-11-15',observacion='')).encode()
        with urlopen(Request(self.url+'/api/reviews/'+self.case['id'],data=body,headers={'Content-Type':'application/json','Origin':self.url})) as r:
            self.assertTrue(json.load(r)['ok'])
        with urlopen(self.url+'/api/reviews') as r:
            self.assertEqual(json.load(r)['reviews'][self.case['id']]['revisado_por'],'Prueba HTTP')
        with urlopen(self.url+'/api/export/xlsx') as r:
            self.assertEqual(r.read(2),b'PK')


if __name__=='__main__':unittest.main()
