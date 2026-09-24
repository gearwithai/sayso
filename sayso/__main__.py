import sys

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        # Checks the installed app works (used by the automated Windows test). Runs in a throwaway
        # profile folder, so it never touches the user's settings.
        from sayso.selftest import main as selftest
        sys.exit(selftest(sys.argv[sys.argv.index("--selftest") + 1:]))
    from sayso.app import main
    main()
