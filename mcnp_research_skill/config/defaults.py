"""Built-in default profile for MCNP research skill."""

DEFAULT_PROFILE: dict = {
    "active_profile": "default",
    "profiles": {
        "default": {
            "mcnp": {
                "executable": "",
                "mpi_command": "",
                "version": "mcnp5",
            },
            "detector": {
                "reference_points": {
                    "aluminum_surface": {
                        "name": "铝壳表面",
                        "z": -0.34,
                        "short_label": "Al",
                    },
                    "crystal_front": {
                        "name": "晶体前表面",
                        "z": 0.0,
                        "short_label": "Front",
                    },
                    "crystal_center": {
                        "name": "晶体几何中心",
                        "z": 3.81,
                        "short_label": "Center",
                    },
                },
            },
            "nuclides": {
                "single_energy": {
                    "Am-241": [0.0595],
                    "Ba-133": [0.081, 0.356],
                    "Cs-137": [0.662],
                    "Co-60": [1.173, 1.332],
                },
                "composite_sources": {},
            },
            "plotting": {
                "preferred_fonts": [
                    "SimHei",
                    "Microsoft YaHei",
                    "Arial Unicode MS",
                ],
            },
            "origin": {
                "enabled": False,
                "temp_dir": "",
                "process_names": [],
            },
        },
    },
}
