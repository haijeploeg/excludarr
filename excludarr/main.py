from cement import App, TestApp, init_defaults
from cement.core.exc import CaughtSignal
from .core.exc import ExcludarrError
from .controllers.base import Base

# configuration defaults
CONFIG = init_defaults("general")
CONFIG["general"]["country"] = "NL"
CONFIG["general"]["providers"] = ["netflix"]


class Excludarr(App):
    """Exclude Streaming (Rad/Son)arr primary application."""

    class Meta:
        label = "excludarr"

        # configuration defaults
        config_defaults = CONFIG
        config_files = ["./.excludarr.yml"]

        # call sys.exit() on close
        exit_on_close = True

        # load additional framework extensions
        extensions = [
            "yaml",
            "colorlog",
            "print",
        ]

        # configuration handler
        config_handler = "yaml"

        # configuration file suffix
        config_file_suffix = ".yml"

        # set the log handler
        log_handler = "colorlog"

        # register handlers
        handlers = [
            Base,
        ]


def main():
    with Excludarr() as app:
        try:
            app.run()

        except AssertionError as e:
            print("AssertionError > %s" % e.args[0])
            app.exit_code = 1

            if app.debug is True:
                import traceback

                traceback.print_exc()

        except ExcludarrError as e:
            print("ExcludarrError > %s" % e.args[0])
            app.exit_code = 1

            if app.debug is True:
                import traceback

                traceback.print_exc()

        except CaughtSignal as e:
            # Default Cement signals are SIGINT and SIGTERM, exit 0 (non-error)
            print("\n%s" % e)
            app.exit_code = 0


if __name__ == "__main__":
    main()
