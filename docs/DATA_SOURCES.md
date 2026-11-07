# Knowledge Base Sources

## Generated datasets

`data_kb/missions_kb.json` is generated from the GTA Wiki MediaWiki API. Each mission record carries its article title, URL and license label. The site reports CC BY-SA licensing; derivative content must retain attribution and comply with the applicable ShareAlike terms. This dataset is currently English-first. `title_zh` is populated only where this project already had a reviewed translation; untranslated titles remain `null` rather than machine-invented.

`data_kb/world_pois.json` contains 1,378 upstream native-coordinate rows: 844 interior position records nested under 385 MLO entries, 32 garages, 345 soda machines and 157 gas pumps. Source-row IDs preserve all entries, including coincident positions. The file also accepts one-time engine exports from `%TEMP%\gtav_engine_static_pois.json`; the engine export is empty until the updated SHVDN script is loaded by Story Mode. The DurtyFree repository has no declared license, so check its current terms before redistribution or making this repository public.

`data_kb/collectibles_map.json` is a field projection of `danharper/GTAV` `locations.json` (WTFPL). Its `lat` and `lng` values remain the source site's custom Google Maps coordinates, not GTA world X/Y/Z. The source provides 50 spaceship parts, 50 letter scraps, 50 stunt jumps, 50 under-bridge flights, 30 nuclear waste markers and 12 money markers. It does not provide all requested armor/weapon pickups, service locations, tunnel entrances or peyote plants. The C# game-engine export may add map Blips, but it does not automatically discover unmarked world pickups.

`data_kb/entity_catalog.json` contains selected fields from `DurtyFree/gta-v-data-dumps` (`vehicles.json`, `weapons.json`, `zones.json`). The upstream repository has no declared license in GitHub metadata. Attribution is recorded, but its terms should be checked before this repository is made public or the data is redistributed.

`data_kb/mission_script_catalog.json` contains C source **filenames only** from `root-cause/v-decompiled-scripts`; no decompiled source code is copied. The upstream repository has no declared license and is archived. Script filename similarity is not enough to assert that a filename is the live Story Mode script ID; the mission guide sets `script_id` only where already verified. Other records have `script_id: null` and use a stable Wiki-derived `catalog_key`.

The current GTA Wiki parser finds 73 story-table rows and 55 separate side-table entries (43 Strangers and Freaks rows, plus family, Dr. Friedlander and Lester assassination side entries). The current generated library has 128 unique titles: 94 records with both walkthrough and gold objectives, 6 walkthrough-only, 6 gold-only and 22 catalog-only. Gold objectives are not listed for every optional activity. `data_completeness` separates source omissions from extracted content; `gold_medal_criteria` mirrors the sourced requirements. These statuses do not claim every optional activity has a medal checklist or a complete walkthrough. `mission_number` is the directory row number, not a required playthrough sequence.

The map source currently covers 50 spaceship parts, 50 letter scraps, 50 stunt jumps, 50 under-bridge flights, 30 nuclear waste markers and 12 hidden money markers. It does not cover all requested collectibles (including peyote plants), armor/weapon pickups, service locations, or tunnel entrances. These remain follow-up data tasks; `world_pois.json` stays empty until verified GTA world coordinates are available.

## Rebuild

From the repository root, run:

```powershell
py scripts\build_full_kb.py
```

The command refreshes GitHub-derived indexes, native-coordinate POIs, the mission script filename catalog and (unless `--skip-missions` is passed) mission pages, then writes `data_kb/sources_manifest.json`. After starting Story Mode with the updated C# script, run it again to merge the engine Blip export. Network availability and upstream page/API changes can affect completeness; inspect printed counts and each record's `data_completeness` after a run.
