'''
+-----------------------------------------------------------------------------+
+  Default Resolution Precedence
+-----------------------------------------------------------------------------+
+  Explicitly set
+  > config.set(...)
+-----------------------------------------------------------------------------+
+  Set in CLI flags
+  > app --flag=value
+-----------------------------------------------------------------------------+
+  Environment
+  > MYAPP_FLAG=dotheneedful
+-----------------------------------------------------------------------------+
+  Config file
+  + Loaded and optionally watched based on a list of paths, config file
+    names, and formats
+-----------------------------------------------------------------------------+
+  Key/Value store
+  + Incorporates loaded values from a store like
+-----------------------------------------------------------------------------+
+  Defaults
+  > config.set_default('flag', 'trogdor')
+-----------------------------------------------------------------------------+

What is an arg?
+ A canonical name that the program will use to refer to it internally
+ One of more flags
+ An optional default value
+ Bindings to various environments:
  + 'id' comes from 'SPF_ID' given an environment binding with prefix='SPF'
     and default variable name.  It can also take the value of 'SPF_ALT_ID'
     if 'alt_id' (any case) is given as an alias.
  + 'redis.host' comes from conf['redis']['host'], or conf['redis.host']
    if specified. (Dot separated values are searched for explicitly, then
    split and traversed)
  + Bindings should default to the simplest thing possible (which there will
    no doubt be debate over :-) For example, 'redis.host' would convert to
    'REDIS_HOST' or the prefixed 'SPF_REDIS_HOST'.
  + Can we detect and error on colliding bindings? ('redis_host' and
  'redis.host' would both map to 'REDIS_HOST')

'''
import itertools
import logging
import os


log = logging.getLogger(__name__)


def resolve_in_config(config, key):
    '''
    Recursively resolve `key` in `config`.  Dot-separated keys are processed by
    first trying to match them as full strings against the top-level keys of
    `config`, and are then split and matches attempted against matching
    subkeys.

    One limitation here is that we don't want want to try all combinations. If
    we're looking for the key 'redis.prod.host', this function will look for
    the full key, then recurse on the key 'redis'; if the key 'redis.prod'
    exists, it will not be matched.

    In general, the resolution steps work as they do for flexibility across
    configuration strategies, not within a single strategy.  If you find
    yourself using all of the features of this library, you should probably
    reconsider and standardize on a more opinionated approach.
    '''
    if key in config:
        return config[key]

    first, _, rest = key.partition('.')
    if first in config:
        return resolve_in_config(config[first], rest)

    return None


class Config(object):
    '''
    Implements overlay configuration with precedence taken from the Viper
    library (https://github.com/spf13/viper)
    '''

    def __init__(self, parser=None):
        self.parser = parser

        self.explicit_config = MutableConfig()

        # TODO(davehughes): add flags from argparse
        self.flags_config = ArgparseConfig()
        self.environment_config = EnvironmentConfig()

        # TODO(davehughes): path/watch/etc.
        self.file_config = FileConfig(None)
        self.key_value_config = KeyValueConfig()

        # TODO(davehughes): add defaults from argparse
        self.defaults_config = MutableConfig()
        self.aliases = {}

        self.configs = [
            self.explicit_config,
            self.flags_config,
            self.environment_config,
            self.file_config,
            self.key_value_config,
            self.defaults_config,
            ]

    # --- argparse integration ---
    def parse_args(self, args):
        opts = self.parser.parse_args(args)
        self.flags_config.update(opts)

        # Get parser defaults
        # subparsers = None
        # for action in self.parser._actions:
        #     if type(action) == argparse._SubParsersAction:
        #         subparsers = action.choices

        return opts

    # --- API emulation ---

    # --- Base watch functionality ---
    def watch_config(self):
        for config in self.configs:
            config.watch()

    def unwatch_config(self):
        for config in self.configs:
            config.unwatch()

    def on_config_change(self, listener):
        for config in self.configs:
            config.on_config_change(listener)

    # --- File config ---
    def read_config(self, config_string, codec='json'):
        '''
        TODO: read an actual string in with the specified format/codec
        '''
        pass

    def set_config_name(self, name):
        self.file_config.set_config_name(name)

    def add_config_path(self, path):
        self.file_config.add_config_path(path)

    def read_in_config(self):
        self.file_config.read_in_config()

    # --- Core get/set ---
    def get(self, attr):
        res = self.get_debug(attr)
        if not res:
            return None

        _, _, value = res
        return value

    def get_debug(self, attr):
        keys = [attr] + self.aliases.get(attr, [])
        for config in self.configs:
            for key in keys:
                value = config.get(key)
                if value:
                    return config, key, value

    def set(self, attr, value):
        return self.set_explicit(attr, value)

    def set_explicit(self, attr, value):
        self.explicit_config.set(attr, value)
        return value

    def get_default(self, attr):
        return self.defaults_config.get(attr)

    def set_default(self, attr, value):
        self.defaults_config.set(attr, value)

    def register_alias(self, target, alias):
        '''
        Store this alias and use it as a secondary lookup in get()
        '''
        self.aliases.setdefault(target, []).append(alias)

    # --- Remote K/V ---
    def add_remote_provider(provider_type,
                            secure=False,
                            config_type="json",
                            **provider_config):
        pass


class BaseConfig(object):

    def __init__(self, config=None, watch=False):
        self.change_listeners = []
        self.config = config or {}
        self.watch = watch

    def get(self, attr):
        return resolve_in_config(self.config, attr)

    def on_config_change(self, listener):
        '''
        Store a config change listener to be called when configuration is
        reloaded.
        '''
        self.change_listeners.append(listener)

    def _publish_config_change(self):
        [listener() for listener in self.change_listeners]

    def watch(self):
        self.watch = True

    def unwatch(self):
        self.watch = False


class MutableConfig(BaseConfig):
    '''
    TODO: set/unset variables explicitly in code
    '''
    def __init__(self, config=None, watch=False):
        super(MutableConfig, self).__init__(config=config, watch=watch)

    def set(self, attr, value):
        self.config[attr] = value
        log.info('{}: set {} => {}'.format(
            self.__class__.__name__, attr, value))
        self._publish_config_change()

    def unset(self, attr):
        del self.config[attr]
        log.info('{}: unset {}'.format(self.__class__.__name__, attr))
        self._publish_config_change()

    def replace(self, config):
        self.config = config
        log.info("{}: replaced entire config".format(self.__class__.__name__))
        self._publish_config_change()


class EnvironmentConfig(object):

    def __init__(self, prefix=None):
        self.prefix = prefix
        self.binds = set()

    def get(self, attr):
        # if attr not in self.binds:
        #     return None

        if self.prefix:
            env_var = '{prefix}_{attr}'.format(prefix=self.prefix, attr=attr)
        else:
            env_var = attr
        env_var = env_var.replace('.', '_').upper()
        print env_var

        return os.getenv(env_var)

    def bind(self, attr):
        '''
        Corresponds to `BindEnv`, declaring that we should watch
        for an environment variable called `{env_prefix}_{attr}`
        '''
        self.binds.add(attr)

    def set_env_prefix(self, prefix):
        self.prefix = prefix


class ArgparseConfig(BaseConfig):

    def __init__(self, config=None):
        self.config = config

    def update(self, config):
        self.config = config

    def get(self, attr):
        if not self.config:
            return None
        return getattr(self.config, attr, None)


class FileConfig(MutableConfig):

    def __init__(self, watch=False, codec='json'):
        self.codec = codec

        self.config = {}  # TODO(davehughes)
        self.config_name = None
        self.config_paths = []

        super(FileConfig, self).__init__(self.config, watch=watch)

    def set_config_name(self, name):
        '''
        Save name of config for resolve step
        '''
        self.config_name = name

    def add_config_path(self, path):
        '''
        Add path for resolving config
        '''
        self.config_paths.append(path)

    def resolve_config_file(self):
        # Generate set of paths from directory/config/extension combinations
        paths = self.config_paths
        config_names = [self.config_name]
        extensions = ['.json', '.yaml', '.toml']
        path_param_set = itertools.product(paths, config_names, extensions)
        resolve_paths = [
            os.path.join(path, '{}{}'.format(config_name, extension))
            for (path, config_name, extension)
            in path_param_set
            ]

        # Find the first matching file, or short-circuit if none is found
        resolved_paths = [p for p in resolve_paths if os.path.isfile(p)]
        if not resolved_paths:
            return None, None

        # Resolve codec based on file extension
        resolved_path = resolved_paths[0]
        _, codec_name = os.path.splitext(resolved_path)
        codec_name = codec_name.lstrip('.')
        codec = CODECS.get(codec_name)()

        return resolved_path, codec

    def read_in_config(self):
        '''
        Resolve and read config file, raising an error if
        things go south.
        '''
        config_file, codec = self.resolve_config_file()
        with open(config_file, 'r') as f:
            content = f.read()
            new_config = codec.loads(content)
            # TODO(davehughes): validate new config before swapping
            self.replace(new_config)


class KeyValueConfig(MutableConfig):
    '''
    + what do the backends/configurations look like for this?
    + how does watching work?
    '''
    def __init__(self):
        self.config = {}

    def get(self, attr):
        return self.config.get(attr)


class EtcdConfig(object):

    def __init__(self,
                 etcd_url="http://127.0.0.1:4001",
                 etcd_config_file="/config/hugo.json",
                 etcd_gpg_key="/etc/secrets/mykeyring.gpg"):
        pass


class ConsulConfig(object):
    '''TODO'''
    pass


def JSONCodec():
    import json
    return json


class YAMLCodec(object):

    def loads(self, input_):
        import ruamel.yaml as yaml
        return yaml.load(input_)

    def dumps(self, obj):
        import ruamel.yaml as yaml
        return yaml.dump(obj)


def TOMLCodec():
    import toml
    return toml


CODECS = {
    'json': JSONCodec,
    'yaml': YAMLCodec,
    'toml': TOMLCodec,
    }
