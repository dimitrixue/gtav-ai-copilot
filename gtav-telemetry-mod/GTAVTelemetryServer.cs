using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using GTA;
using GTA.Math;
using GTA.Native;

namespace GTAVCopilotTelemetry
{
    public class GTAVTelemetryMod : Script
    {
        private readonly string _telemetryFilePath;

        private static readonly string[] KnownMissionScripts = new string[]
        {
            "prologue1", "armenian1", "armenian2", "armenian3",
            "family1", "family2", "family3", "family4", "family5", "family6",
            "lester1", "jewelry_setup1", "jewelry_prep1a", "jewelry_prep1b", "jewelry_prep2a", "jewelry_heist",
            "trevor1", "trevor2", "trevor3", "chinese1", "chinese2",
            "fbi1", "fbi2", "fbi3", "fbi4_intro", "fbi4_prep1", "fbi4_prep2", "fbi4", "fbi5a",
            "docks_setup", "docks_prep1", "docks_prep2b", "docks_heista", "docks_heistb",
            "carsteal1", "carsteal2", "carsteal3", "carsteal4",
            "solomon1", "solomon2", "solomon3", "martin1", "exile1", "exile2", "exile3",
            "rural_bank_setup", "rural_bank_prep1", "rural_bank_heist",
            "Michael1", "Michael2", "Michael3", "Michael4",
            "agency_heist1", "agency_heist2", "agency_heist3a", "agency_heist3b",
            "finale_heist1", "finale_heist2_intro", "finale_heist_prepa", "finale_heist_prepb",
            "finale_heist2a", "finale_heist2b", "finalea", "finaleb", "finalec1", "finalec2",
            "assassin_bus", "assassin_hooker", "assassin_multi", "assassin_rankup", "assassin_valet",
            "tonya1", "tonya2", "tonya3", "tonya4", "tonya5",
            "hao1", "paparazzo1", "paparazzo2", "paparazzo3", "omega1", "omega2", "dreyfuss1"
        };

        public GTAVTelemetryMod()
        {
            _telemetryFilePath = Path.Combine(Path.GetTempPath(), "gtav_ai_telemetry.json");
            Tick += OnTick;
            Interval = 200;
        }

        private void OnTick(object sender, EventArgs e)
        {
            try
            {
                Ped playerPed = Game.Player.Character;
                if (playerPed == null || !playerPed.Exists()) return;

                Vector3 pos = playerPed.Position;
                float heading = playerPed.Heading;
                string protagonist = "Unknown";
                int modelHash = playerPed.Model.Hash;
                if (modelHash == (int)PedHash.Michael) protagonist = "Michael";
                else if (modelHash == (int)PedHash.Franklin) protagonist = "Franklin";
                else if (modelHash == (int)PedHash.Trevor) protagonist = "Trevor";

                string zoneName = World.GetZoneLocalizedName(pos);
                string streetName = World.GetStreetName(pos);
                bool isMissionActive = Game.IsMissionActive;
                string activeMissionScript = "freeroam";
                foreach (string scriptName in KnownMissionScripts)
                {
                    int runningCount = Function.Call<int>(
                        Hash.GET_NUMBER_OF_THREADS_RUNNING_THE_SCRIPT_WITH_THIS_HASH,
                        Game.GenerateHash(scriptName));
                    if (runningCount > 0)
                    {
                        activeMissionScript = scriptName;
                        break;
                    }
                }

                string objectivesJson = GetActiveObjectiveBlipsJson(pos);
                string vehicleInfo = "On Foot";
                if (playerPed.IsInVehicle())
                {
                    Vehicle veh = playerPed.CurrentVehicle;
                    if (veh != null && veh.Exists())
                        vehicleInfo = string.Format(CultureInfo.InvariantCulture, "{0} (HP: {1}/{2})", veh.LocalizedName, veh.Health, veh.MaxHealth);
                }

                string json = string.Format(
                    CultureInfo.InvariantCulture,
                    "{{\n" +
                    "  \"timestamp\": {0},\n" +
                    "  \"protagonist\": \"{1}\",\n" +
                    "  \"is_mission_active\": {2},\n" +
                    "  \"active_mission_script\": \"{3}\",\n" +
                    "  \"location\": {{\n" +
                    "    \"x\": {4:F2},\n    \"y\": {5:F2},\n    \"z\": {6:F2},\n    \"heading\": {7:F1},\n" +
                    "    \"zone_name\": \"{8}\",\n    \"street_name\": \"{9}\"\n  }},\n" +
                    "  \"player_status\": {{\n    \"hp\": {10},\n    \"max_hp\": {11},\n" +
                    "    \"armor\": {12},\n    \"wanted_level\": {13},\n    \"money\": {14},\n" +
                    "    \"current_weapon\": \"{15}\",\n    \"vehicle\": \"{16}\"\n  }},\n" +
                    "  \"active_objectives\": {17}\n}}",
                    DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(), EscapeJson(protagonist),
                    isMissionActive ? "true" : "false", EscapeJson(activeMissionScript),
                    pos.X, pos.Y, pos.Z, heading, EscapeJson(zoneName), EscapeJson(streetName),
                    playerPed.Health - 100, playerPed.MaxHealth - 100, playerPed.Armor,
                    Game.Player.WantedLevel, Game.Player.Money, playerPed.Weapons.Current.Hash.ToString(),
                    EscapeJson(vehicleInfo), objectivesJson);

                string tempFile = _telemetryFilePath + ".tmp";
                File.WriteAllText(tempFile, json, Encoding.UTF8);
                File.Copy(tempFile, _telemetryFilePath, true);
            }
            catch (Exception)
            {
            }
        }

        private string GetActiveObjectiveBlipsJson(Vector3 playerPos)
        {
            List<string> blipEntries = new List<string>();
            foreach (Blip b in World.GetAllBlips())
            {
                if (b == null || !b.Exists()) continue;
                bool isMissionTarget = b.ShowsRoute || b.IsFlashing || b.Color == BlipColor.Yellow ||
                                       b.Color == BlipColor.Red || b.Color == BlipColor.Blue || b.Color == BlipColor.Green;
                if (isMissionTarget && b.Type != 4)
                {
                    Vector3 bPos = b.Position;
                    float dist = World.GetDistance(playerPos, bPos);
                    string role = b.Color.ToString();
                    if (b.Color == BlipColor.Yellow) role = "Destination_Route";
                    else if (b.Color == BlipColor.Red) role = "Enemy_Target";
                    else if (b.Color == BlipColor.Blue) role = "Ally_Target";
                    else if (b.Color == BlipColor.Green) role = "Vehicle_Or_Item_Target";
                    string entry = string.Format(CultureInfo.InvariantCulture,
                        "{{\"role\":\"{0}\",\"name\":\"{1}\",\"x\":{2:F1},\"y\":{3:F1},\"z\":{4:F1},\"distance_m\":{5:F1},\"has_gps_route\":{6}}}",
                        role, EscapeJson(b.Name), bPos.X, bPos.Y, bPos.Z, dist, b.ShowsRoute ? "true" : "false");
                    blipEntries.Add(entry);
                    if (blipEntries.Count >= 8) break;
                }
            }
            return "[" + string.Join(",", blipEntries.ToArray()) + "]";
        }

        private string EscapeJson(string input)
        {
            if (string.IsNullOrEmpty(input)) return "";
            return input.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", " ").Replace("\r", "");
        }
    }
}
