"""Pruebas con datos ficticios temporales; no necesitan videos ni archivos privados."""
import csv
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import server

FIELDS = ['n','subconjunto','familia','original','archivo','aviso_simulador','prioridad_simulador',
          'fotogramas_con_efecto_pct','estado_conocido','que_mirar','resultado','revisado_por','fecha','observacion']


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.csv=self.root/'lista_ficticia.csv'
        with self.csv.open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=FIELDS);writer.writeheader()
            for n in range(1,291):
                writer.writerow(dict(n=n,subconjunto='test_single',familia='desenfoque',original=f'DEMO_{n}',
                    archivo=f'editados/prueba_single_original_sin_perdida/DEMO/DEMO_{n}_clean_x__blur_rostro_2.mp4'))

    def test_catalog_accepts_external_csv_without_dataset(self):
        catalog=server.Catalog(self.root,self.csv,self.root/'privada.xlsx')
        self.assertEqual(len(catalog.records),290)
        self.assertEqual(sum(r['required'] for r in catalog.records),38)
        self.assertFalse(any(r['available'] for r in catalog.records))
        self.assertEqual(catalog.template_path,self.root/'privada.xlsx')

    def test_reviews_use_supplied_store_and_persist_without_media(self):
        catalog=server.Catalog(self.root,self.csv)
        store=server.ReviewStore(self.root/'revision_prueba.json')
        store.save(catalog.byn[104],dict(resultado='no se nota',revisado_por='Persona de prueba',
            fecha='2026-11-16',observacion='Prueba con datos ficticios'))
        self.assertEqual(server.ReviewStore(store.path).snapshot()[catalog.byn[104]['id']]['resultado'],'no se nota')

    def test_explicit_ffmpeg_takes_priority_over_environment(self):
        with patch.dict(os.environ,{'LSP_FFMPEG':'environment-ffmpeg'}):
            playback=server.BrowserPlayback(self.root,cache_dir=self.root/'cache',ffmpeg='explicit-ffmpeg')
            self.assertEqual(playback.ffmpeg,'explicit-ffmpeg')

    def test_missing_xlsx_template_has_actionable_error(self):
        catalog=server.Catalog(self.root,self.csv,self.root/'faltante.xlsx')
        with self.assertRaisesRegex(ValueError,'plantilla'):
            server.xlsx_bytes(catalog,{})


if __name__=='__main__':unittest.main()
