# Knowledge Base Sources

## Generated datasets

`data_kb/missions_kb.json` is generated from the GTA Wiki MediaWiki API. Each mission record carries its article title, URL and license label. The site reports CC BY-SA licensing; derivative content must retain attribution and comply with the applicable ShareAlike terms. This dataset is currently English-first. `title_zh` is populated only where this project already had a reviewed translation; untranslated titles remain `null` rather than machine-invented.

`data_kb/collectibles_map.json` is a field projection of `danharper/GTAV` `locations.json` (WTFPL). Its `lat` and `lng` values are the source site's custom Google Maps coordinates. They are not GTA world X/Y/Z and must not be passed to in-game marker APIs without a verified transform. The upstream data currently provides collectibles and map markers, but not the requested armor, weapon pickup and peyote sets.

`data_kb/entity_catalog.json` contains selected fields from `DurtyFree/gta-v-data-dumps` (`vehicles.json`, `weapons.json`, `zones.json`). The upstream repository has no declared license in GitHub metadata. Attribution is recorded, but its terms should be checked before this repository is made public or the data is redistributed.

`data_kb/mission_script_catalog.json` contains C source **filenames only** from `root-cause/v-decompiled-scripts`; no decompiled source code is copied. The upstream repository has no declared license and is archived. Script filename similarity is not enough to assert that a filename is the live Story Mode script ID; the mission guide sets `script_id` only where already verified. Other records have `script_id: null` and use a stable Wiki-derived `catalog_key`.

The current GTA Wiki parser finds 73 story-table rows and 55 separate side-table entries (43 Strangers and Freaks rows, plus family, Dr. Friedlander and Lester assassination side entries). The overview page itself describes the in-game statistics count as 69; the difference is caused by optional setup/branch entries, while side tables aggregate some multi-part series. This build preserves source rows and provenance instead of deleting or fabricating records to force 69/58 counts. The current generated library has 128 unique titles: 94 records with both walkthrough and gold objectives, 6 walkthrough-only, 6 gold-only and 22 catalog-only. `source_counts` and `guide_status` expose these distinctions. `mission_number` is the directory row number, not a required playthrough sequence.

The map source currently covers 50 spaceship parts, 50 letter scraps, 50 stunt jumps, 50 under-bridge flights, 30 nuclear waste markers and 12 hidden money markers. It does not cover all requested collectibles (including peyote plants), armor/weapon pickups, service locations, or tunnel entrances. These remain follow-up data tasks; `world_pois.json` stays empty until verified GTA world coordinates are available.

## Rebuild

From the repository root, run:

```powershell
py scripts\build_full_kb.py
```

The command refreshes the GitHub-derived indexes, mission script filename catalog and mission pages, then writes `data_kb/sources_manifest.json`. Use `--skip-missions` to refresh only GitHub datasets. Network availability and upstream page/API changes can affect completeness; inspect the printed counts and per-record `guide_status` after each run.
