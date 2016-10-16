import os
import shutil
import tempfile
import unittest

from pyviper import core


class BaseConfigTest(unittest.TestCase):

    def assertConfigExpectations(self, config, expectations):
        for lookup, expected in expectations.iteritems():
            actual = config.get(lookup)
            self.assertEqual(actual, expected,
                'Lookup [{}]: Expected value {} did not match actual value {}'.format(lookup, expected, actual))


class TestEnvironmentConfig(BaseConfigTest):

    def test_non_prefixed(self):
        os.environ['VAR1'] = 'test-value'
        config = core.EnvironmentConfig()

        self.assertConfigExpectations(config, {
            'VAR1': 'test-value',
            'VAR2': None,
            })

    def test_prefixed(self):
        config = core.EnvironmentConfig()
        os.environ['TEST_VAR1'] = 'test-value'
        config.set_env_prefix('TEST')
        self.assertConfigExpectations(config, {
            'VAR1': 'test-value',
            'VAR2': None,
            })


class TestFileConfig(unittest.TestCase):
    def test(self):

        # Generate temporary config file
        config = {
            'redis': {
                'host': 'localhost',
                'port': 6379,
                },
            'redis.host': 'example.com',
            }
        tmpdir = tempfile.mkdtemp()
        try:
            codec = core.JSONCodec()
            tmp_config_path = os.path.join(tmpdir, 'config.json')
            with open(tmp_config_path, 'w') as f:
                f.write(codec.dumps(config))

            # Set up file config and probe data
            config = core.FileConfig()
            config.add_config_path(tmpdir)
            config.set_config_name('config')
            config.read_in_config()

            self.assertEqual(config.get('redis.host'), 'example.com')
            self.assertEqual(config.get('redis.port'), 6379)
            self.assertEqual(config.get('unrecognized'), None)
        finally:
            shutil.rmtree(tmpdir)


class TestResolution(unittest.TestCase):

    def test_shallow_dotted_resolution(self):
        config = {
            'redis': {
                'host': 'localhost',
                'port': 6379,
                },
            'redis.host': 'example.com',
            }

        self.assertEqual(
            core.resolve_in_config(config, 'redis.host'),
            'example.com',
            )

        self.assertEqual(
            core.resolve_in_config(config, 'redis.port'),
            6379,
            )

        self.assertEqual(
            core.resolve_in_config(config, 'redis.dolphin'),
            None,
            )


class TestMainConfig(BaseConfigTest):

    def test_environment_overlay(self):
        os.environ['TEST_VAR1'] = 'test-value'
        config = core.Config()

        self.assertConfigExpectations(config, {
            'TEST_VAR1': 'test-value',
            'TEST_VAR2': None,
            })

    def test_environment_with_explicit_override(self):
        os.environ['TEST_VAR1'] = 'test-value'
        config = core.Config()
        self.assertConfigExpectations(config, {
            'TEST_VAR1': 'test-value',
            'TEST_VAR2': None,
            })

        config.set('TEST_VAR1', 'another-value')
        config.set('TEST_VAR2', 'a-second-value')
        self.assertConfigExpectations(config, {
            'TEST_VAR1': 'another-value',
            'TEST_VAR2': 'a-second-value',
            })

    def test_defaults_and_overrides(self):
        os.environ['A'] = '4'

        config = core.Config()
        config.set_default('A', 1)
        config.set_default('B', 2)
        config.set_default('C', 3)

        self.assertConfigExpectations(config, {
            'A': '4',
            'B': 2,
            'C': 3,
            'D': None,
            })

    def test_aliases(self):
        config = core.Config()
        config.register_alias('port', 'service_port')
        config.set_default('service_port', 1234)

        self.assertConfigExpectations(config, {
            'port': 1234,
            'service_port': 1234,
            'nonexistent': None,
            })

    def test_dotted_resolution(self):
        os.environ['REDIS_PORT'] = '1234'

        config = core.Config()
        config.set('redis', {'db': 10})
        config.set_default('redis.host', 'example.com')

        self.assertConfigExpectations(config, {
            'redis.db': 10,
            'redis.port': '1234',
            'redis.host': 'example.com',
            'nonexistent': None,
            })


class TestConfigCodecs(BaseConfigTest):

    def test_codecs(self):
        codecs = [
            core.JSONCodec(),
            core.YAMLCodec(),
            core.TOMLCodec(),
            ]
        test_input = {'redis.host': 'example.com:6379'}

        for codec in codecs:
            loaded_config = codec.loads(codec.dumps(test_input))
            self.assertEqual(loaded_config.get('redis.host'),
                             'example.com:6379')
            self.assertEqual(loaded_config.get('nonexistent'), None)
