using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Drawing;
using System.Text;
using System.Web.Script.Serialization;
using GTA;
using GTA.Math;
using GTA.Native;
using GTA.UI;

namespace GTAVCopilotTelemetry
{
    public class GTAVTelemetryMod : Script
    {
        private readonly string _telemetryFilePath;
        private readonly string _commandsFilePath;
        private readonly string _staticPoisFilePath;
        private readonly JavaScriptSerializer _serializer = new JavaScriptSerializer();
        private DateTime _lastIoUtc = DateTime.MinValue;
        private DateTime _commandsExpireUtc = DateTime.MinValue;
        private bool _staticPoisExported;
        private List<Dictionary<string, object>> _drawMarkers = new List<Dictionary<string, object>>();
        private string _notification;

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
            _commandsFilePath = Path.Combine(Path.GetTempPath(), "gtav_ai_commands.json");
            _staticPoisFilePath = Path.Combine(Path.GetTempPath(), "gtav_engine_static_pois.json");
            Tick += OnTick;
            Interval = 0;
        }

        private void OnTick(object sender, EventArgs e)
        {
            try
            {
                Ped playerPed = Game.Player.Character;
                if (playerPed == null || !playerPed.Exists()) return;

                if (!_staticPoisExported)
                {
                    ExportStaticBlips();
                    _staticPoisExported = true;
                }

                DateTime now = DateTime.UtcNow;
                if ((now - _lastIoUtc).TotalMilliseconds >= 200)
                {
                    ReadCommands(now);
                    WriteTelemetry(playerPed);
                    _lastIoUtc = now;
                }
                DrawCommands(playerPed);
            }
            catch (Exception)
            {
            }
        }

        private void WriteTelemetry(Ped playerPed)
        {
            try
            {

                Vector3 pos = playerPed.Position;
                float heading = playerPed.Heading;
                string protagonist = "Unknown";
                int modelHash = playerPed.Model.Hash;
                if (modelHash == unchecked((int)PedHash.Michael)) protagonist = "Michael";
                else if (modelHash == unchecked((int)PedHash.Franklin)) protagonist = "Franklin";
                else if (modelHash == unchecked((int)PedHash.Trevor)) protagonist = "Trevor";

                string zoneName = World.GetZoneLocalizedName(pos);
                string streetName = World.GetStreetName(pos);
                bool isMissionActive = Game.IsMissionActive;
                string activeMissionScript = "freeroam";
                foreach (string scriptName in KnownMissionScripts)
                {
                    int runningCount = Function.Call<int>(
                        Hash.GET_NUMBER_OF_THREADS_RUNNING_THE_SCRIPT_WITH_THIS_HASH,
                        unchecked((int)Game.GenerateHash(scriptName)));
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

                WriteAtomic(_telemetryFilePath, json);
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
                bool isMissionTarget = b.ShowRoute || b.IsFlashing || b.Color == BlipColor.Yellow ||
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
                    OutputArgument screenX = new OutputArgument();
                    OutputArgument screenY = new OutputArgument();
                    bool isOnScreen = Function.Call<bool>((Hash)0x34E82F05DF2974F5,
                        bPos.X, bPos.Y, bPos.Z, screenX, screenY);
                    float sx = isOnScreen ? screenX.GetResult<float>() : -1f;
                    float sy = isOnScreen ? screenY.GetResult<float>() : -1f;
                    string entry = string.Format(CultureInfo.InvariantCulture,
                        "{{\"role\":\"{0}\",\"name\":\"{1}\",\"x\":{2:F1},\"y\":{3:F1},\"z\":{4:F1},\"distance_m\":{5:F1},\"has_gps_route\":{6},\"screen_x\":{7:F5},\"screen_y\":{8:F5},\"is_on_screen\":{9}}}",
                        role, EscapeJson(b.Name), bPos.X, bPos.Y, bPos.Z, dist, b.ShowRoute ? "true" : "false",
                        sx, sy, isOnScreen ? "true" : "false");
                    blipEntries.Add(entry);
                    if (blipEntries.Count >= 8) break;
                }
            }
            return "[" + string.Join(",", blipEntries.ToArray()) + "]";
        }

        private void ExportStaticBlips()
        {
            try
            {
                List<object> records = new List<object>();
                foreach (Blip blip in World.GetAllBlips())
                {
                    if (blip == null || !blip.Exists()) continue;
                    Vector3 p = blip.Position;
                    records.Add(new Dictionary<string, object>
                    {
                        { "name", blip.Name ?? "" }, { "sprite", (int)blip.Sprite },
                        { "x", p.X }, { "y", p.Y }, { "z", p.Z }, { "category", BlipCategory((int)blip.Sprite) }
                    });
                }
                WriteAtomic(_staticPoisFilePath, _serializer.Serialize(new Dictionary<string, object>
                {
                    { "exported_at", DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() }, { "pois", records }
                }));
            }
            catch (Exception)
            {
            }
        }

        private static string BlipCategory(int sprite)
        {
            switch (sprite)
            {
                case 72: return "vehicle_mod_shop";
                case 110: return "weapon_shop";
                case 40: return "safehouse";
                case 61: return "hospital";
                case 73: return "clothing_shop";
                case 362: return "mask_shop";
                case 36: return "cable_car";
                default: return "engine_static_blip";
            }
        }

        private void ReadCommands(DateTime now)
        {
            if (!File.Exists(_commandsFilePath))
            {
                _drawMarkers.Clear();
                _notification = null;
                _commandsExpireUtc = DateTime.MinValue;
                return;
            }
            try
            {
                string raw = File.ReadAllText(_commandsFilePath, Encoding.UTF8);
                Dictionary<string, object> root = _serializer.Deserialize<Dictionary<string, object>>(raw);
                if (root == null) throw new InvalidDataException("Command file must contain a JSON object.");
                long expires = Convert.ToInt64(root.ContainsKey("expires_at") ? root["expires_at"] : 0, CultureInfo.InvariantCulture);
                if (expires <= DateTimeOffset.UtcNow.ToUnixTimeMilliseconds())
                {
                    _drawMarkers.Clear();
                    _notification = null;
                    _commandsExpireUtc = DateTime.MinValue;
                    return;
                }
                _commandsExpireUtc = DateTimeOffset.FromUnixTimeMilliseconds(expires).UtcDateTime;
                _drawMarkers = new List<Dictionary<string, object>>();
                object markerValue;
                if (root.TryGetValue("draw_3d_markers", out markerValue))
                {
                    object[] markers = markerValue as object[];
                    if (markers != null)
                        foreach (object value in markers)
                        {
                            Dictionary<string, object> marker = value as Dictionary<string, object>;
                            if (marker != null) _drawMarkers.Add(marker);
                        }
                }
                string notification = root.ContainsKey("in_game_notification") ? root["in_game_notification"] as string : null;
                if (!string.IsNullOrEmpty(notification) && notification != _notification)
                {
                    Screen.ShowSubtitle(notification, 5000);
                    _notification = notification;
                }
            }
            catch (Exception)
            {
                _drawMarkers.Clear();
            }
        }

        private void DrawCommands(Ped playerPed)
        {
            if (DateTime.UtcNow > _commandsExpireUtc) return;
            Vector3 playerPos = playerPed.Position;
            foreach (Dictionary<string, object> marker in _drawMarkers)
            {
                try
                {
                    float x = Number(marker, "x"), y = Number(marker, "y"), z = Number(marker, "z");
                    if (z == 0f) z = World.GetGroundHeight(new Vector2(x, y));
                    Vector3 target = new Vector3(x, y, z);
                    object[] colorValues = marker.ContainsKey("color") ? marker["color"] as object[] : null;
                    int[] rgba = colorValues == null ? null : Array.ConvertAll(colorValues, value => Convert.ToInt32(value, CultureInfo.InvariantCulture));
                    Color color = rgba != null && rgba.Length >= 4
                        ? Color.FromArgb(Clamp(rgba[3]), Clamp(rgba[0]), Clamp(rgba[1]), Clamp(rgba[2]))
                        : Color.FromArgb(180, 0, 255, 200);
                    World.DrawMarker(MarkerType.VerticalCylinder, target + new Vector3(0f, 0f, 1.5f),
                        new Vector3(0f, 0f, 0f), new Vector3(0f, 0f, 0f), new Vector3(1.2f, 1.2f, 3f),
                        color, false, true, false, null, null, false);
                    object drawLine;
                    if (!marker.TryGetValue("draw_line_from_player", out drawLine) || Convert.ToBoolean(drawLine, CultureInfo.InvariantCulture))
                        Function.Call((Hash)0x6B7256074AE34680,
                            playerPos.X, playerPos.Y, playerPos.Z + 0.5f, target.X, target.Y, target.Z, color.R, color.G, color.B, color.A);
                }
                catch (Exception)
                {
                }
            }
        }

        private static float Number(Dictionary<string, object> values, string key)
        {
            return Convert.ToSingle(values[key], CultureInfo.InvariantCulture);
        }

        private static int Clamp(int value)
        {
            return Math.Max(0, Math.Min(255, value));
        }

        private static void WriteAtomic(string path, string contents)
        {
            string tempFile = path + ".tmp";
            File.WriteAllText(tempFile, contents, new UTF8Encoding(false));
            if (File.Exists(path)) File.Replace(tempFile, path, null);
            else File.Move(tempFile, path);
        }

        private string EscapeJson(string input)
        {
            if (string.IsNullOrEmpty(input)) return "";
            return input.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", " ").Replace("\r", "");
        }
    }
}
