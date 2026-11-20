"""Configuration regressions: no real database or credentials are needed."""
import json
import os
import subprocess
import sys
from django.test import SimpleTestCase

class DeploymentSettingsTests(SimpleTestCase):
    def run_settings(self, **values):
        env = {key:value for key,value in os.environ.items()
               if key not in ('DATABASE_URL', 'DATABASE_ENGINE', 'VERCEL', 'DJANGO_DEBUG')}
        env.update(DJANGO_SECRET_KEY='tests-only', **values)
        script = "from config import settings as s; import json; print(json.dumps({'engine':s.DATABASES['default']['ENGINE'],'hosts':s.ALLOWED_HOSTS,'ssl':s.DATABASES['default'].get('OPTIONS',{}).get('sslmode'),'static':s.STATIC_URL,'secure':getattr(s,'SESSION_COOKIE_SECURE',False),'password':s.DATABASES['default'].get('PASSWORD')}))"
        return subprocess.run([sys.executable, '-c', script],env=env,capture_output=True,text=True)

    def test_vercel_rejects_sqlite(self):
        result=self.run_settings(VERCEL='1')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('SQLite no es persistente',result.stderr)

    def test_vercel_rejects_debug(self):
        result=self.run_settings(VERCEL='1',DJANGO_DEBUG='1')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('DJANGO_DEBUG',result.stderr)

    def test_neon_url_and_secure_defaults(self):
        result=self.run_settings(VERCEL='1',VERCEL_URL='preview.vercel.app',DATABASE_URL='postgresql://demo:p%40ss@db.example.invalid/ushlm?sslmode=require')
        self.assertEqual(result.returncode,0,result.stderr)
        data=json.loads(result.stdout)
        self.assertEqual(data['password'],'p@ss')
        self.assertIn('preview.vercel.app',data['hosts'])
        self.assertEqual(data['ssl'],'require')
        self.assertTrue(data['secure'])
        self.assertEqual(data['static'],'/static/')

    def test_vercel_rejects_unencrypted_connection(self):
        result=self.run_settings(VERCEL='1',DATABASE_URL='postgresql://demo:demo@db.example.invalid/ushlm?sslmode=disable')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('TLS',result.stderr)
