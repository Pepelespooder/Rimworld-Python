using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using RimWorld;
using Verse;

namespace RimworldPython
{
    [StaticConstructorOnStartup]
    public static class PythonBootstrap
    {
        private const string PackageId = "makin.rimworldpython";

        static PythonBootstrap()
        {
            try
            {
                RunStartupScripts();
            }
            catch (Exception ex)
            {
                Log.Error("[Rimworld Python] Loader failed: " + ex);
            }
        }

        private static void RunStartupScripts()
        {
            string modRoot = GetModRoot();
            string assembliesRoot = Path.Combine(modRoot, "Assemblies");
            string dependenciesRoot = Path.Combine(modRoot, "ThirdParty", "IronPython");
            string scriptsRoot = Path.Combine(modRoot, "Scripts");

            if (!Directory.Exists(scriptsRoot))
            {
                Log.Warning("[Rimworld Python] No scripts folder found at " + scriptsRoot);
                return;
            }

            AppDomain.CurrentDomain.AssemblyResolve += (_, args) =>
                ResolveFromAssemblies(dependenciesRoot, args) ??
                ResolveFromAssemblies(assembliesRoot, args);

            Assembly ironPython = LoadAssembly(dependenciesRoot, "IronPython.dll");
            Type pythonType = ironPython.GetType("IronPython.Hosting.Python", true);
            object engine = pythonType.GetMethod("CreateEngine", Type.EmptyTypes).Invoke(null, null);

            ConfigureSearchPaths(engine, scriptsRoot, dependenciesRoot);

            object scope = engine.GetType().GetMethod("CreateScope", Type.EmptyTypes).Invoke(engine, null);
            SetVariable(scope, "mod_root", modRoot);
            SetVariable(scope, "scripts_root", scriptsRoot);
            SetVariable(scope, "log", new Action<string>(message => Log.Message("[Rimworld Python] " + message)));
            SetVariable(scope, "autostart_enabled", new Func<bool>(() => File.Exists(Path.Combine(scriptsRoot, "autostart.enabled"))));
            SetVariable(scope, "load_latest_save", new Func<string>(PythonAutomation.LoadLatestSave));
            SetVariable(scope, "rim", new RimworldPythonApi(scriptsRoot));

            foreach (string scriptPath in Directory.GetFiles(scriptsRoot, "*.py").OrderBy(path => path))
            {
                try
                {
                    ExecuteFile(engine, scriptPath, scope);
                    Log.Message("[Rimworld Python] Loaded IronPython startup script: " + scriptPath);
                }
                catch (Exception ex)
                {
                    Log.Error("[Rimworld Python] Script failed: " + scriptPath + "\n" + ex);
                }
            }
        }

        private static string GetModRoot()
        {
            ModContentPack mod = LoadedModManager.RunningModsListForReading
                .FirstOrDefault(pack => string.Equals(pack.PackageId, PackageId, StringComparison.OrdinalIgnoreCase));

            if (mod != null && !string.IsNullOrEmpty(mod.RootDir))
            {
                return mod.RootDir;
            }

            string assemblyPath = typeof(PythonBootstrap).Assembly.Location;
            DirectoryInfo assembliesDirectory = Directory.GetParent(assemblyPath);
            DirectoryInfo modDirectory = assembliesDirectory != null ? assembliesDirectory.Parent : null;

            if (modDirectory != null)
            {
                return modDirectory.FullName;
            }

            throw new InvalidOperationException("Could not determine mod root for package " + PackageId);
        }

        private static Assembly ResolveFromAssemblies(string assembliesRoot, ResolveEventArgs args)
        {
            string assemblyName = new AssemblyName(args.Name).Name + ".dll";
            string candidatePath = Path.Combine(assembliesRoot, assemblyName);
            return File.Exists(candidatePath) ? Assembly.LoadFrom(candidatePath) : null;
        }

        private static Assembly LoadAssembly(string assembliesRoot, string fileName)
        {
            string path = Path.Combine(assembliesRoot, fileName);
            if (!File.Exists(path))
            {
                throw new FileNotFoundException("Missing IronPython dependency", path);
            }

            return Assembly.LoadFrom(path);
        }

        private static void ConfigureSearchPaths(object engine, string scriptsRoot, string assembliesRoot)
        {
            MethodInfo setSearchPaths = engine.GetType().GetMethod("SetSearchPaths");
            if (setSearchPaths == null)
            {
                return;
            }

            setSearchPaths.Invoke(engine, new object[]
            {
                new[]
                {
                    scriptsRoot,
                    assembliesRoot,
                    Path.Combine(assembliesRoot, "Lib"),
                    Path.Combine(assembliesRoot, "site-packages")
                }
            });
        }

        private static void SetVariable(object scope, string name, object value)
        {
            MethodInfo method = scope.GetType()
                .GetMethods()
                .First(m => m.Name == "SetVariable" && m.GetParameters().Length == 2);

            method.Invoke(scope, new[] { name, value });
        }

        private static void ExecuteFile(object engine, string filePath, object scope)
        {
            MethodInfo method = engine.GetType()
                .GetMethods()
                .First(m =>
                {
                    if (m.Name != "ExecuteFile")
                    {
                        return false;
                    }

                    ParameterInfo[] parameters = m.GetParameters();
                    return parameters.Length == 2 && parameters[0].ParameterType == typeof(string);
                });

            method.Invoke(engine, new[] { filePath, scope });
        }
    }

    public static class PythonAutomation
    {
        public static string LoadLatestSave()
        {
            FileInfo saveFile = GenFilePaths.AllSavedGameFiles
                .OrderByDescending(file => file.LastWriteTimeUtc)
                .FirstOrDefault();

            if (saveFile == null)
            {
                return "No RimWorld save files were found.";
            }

            LongEventHandler.QueueLongEvent(
                () => GameDataSaveLoader.LoadGame(saveFile),
                "LoadingLongEvent",
                false,
                ex => Log.Error("[Rimworld Python] Failed to auto-load save '" + saveFile.Name + "': " + ex),
                false,
                false,
                null);

            return "Queued load for latest save: " + saveFile.Name;
        }

        public static string LoadSave(string saveName)
        {
            FileInfo saveFile = FindSave(saveName);
            if (saveFile == null)
            {
                return "Save not found: " + saveName;
            }

            LongEventHandler.QueueLongEvent(
                () => GameDataSaveLoader.LoadGame(saveFile),
                "LoadingLongEvent",
                false,
                ex => Log.Error("[Rimworld Python] Failed to auto-load save '" + saveFile.Name + "': " + ex),
                false,
                false,
                null);

            return "Queued load for save: " + saveFile.Name;
        }

        private static FileInfo FindSave(string saveName)
        {
            if (string.IsNullOrEmpty(saveName))
            {
                return null;
            }

            string normalized = saveName.EndsWith(".rws", StringComparison.OrdinalIgnoreCase)
                ? saveName
                : saveName + ".rws";

            return GenFilePaths.AllSavedGameFiles.FirstOrDefault(file =>
                string.Equals(file.Name, normalized, StringComparison.OrdinalIgnoreCase) ||
                string.Equals(Path.GetFileNameWithoutExtension(file.Name), saveName, StringComparison.OrdinalIgnoreCase));
        }
    }

    public sealed class RimworldPythonApi
    {
        private readonly string scriptsRoot;

        public RimworldPythonApi(string scriptsRoot)
        {
            this.scriptsRoot = scriptsRoot;
        }

        public void log(string message)
        {
            Log.Message("[Rimworld Python] " + message);
        }

        public void warn(string message)
        {
            Log.Warning("[Rimworld Python] " + message);
        }

        public void error(string message)
        {
            Log.Error("[Rimworld Python] " + message);
        }

        public bool autostart_enabled()
        {
            return File.Exists(Path.Combine(scriptsRoot, "autostart.enabled"));
        }

        public bool game_loaded()
        {
            return Current.Game != null;
        }

        public string program_state()
        {
            return Current.ProgramState.ToString();
        }

        public string current_map_info()
        {
            Map map = Find.CurrentMap;
            if (map == null)
            {
                return "No current map.";
            }

            return map.uniqueID + ": " + map.Size.x + "x" + map.Size.z + ", biome=" + map.Biome.defName;
        }

        public string selected_thing_label()
        {
            Thing thing = Find.Selector != null ? Find.Selector.SingleSelectedThing : null;
            return thing != null ? thing.LabelCap : "No single thing selected.";
        }

        public string selected_pawn_name()
        {
            Pawn pawn = Find.Selector != null ? Find.Selector.SelectedPawns.FirstOrDefault() : null;
            return pawn != null ? pawn.LabelShortCap : "No pawn selected.";
        }

        public string[] colonist_names()
        {
            return PawnsFinder.AllMaps_FreeColonists
                .Select(pawn => pawn.LabelShortCap)
                .ToArray();
        }

        public object[] active_mods()
        {
            return LoadedModManager.RunningModsListForReading
                .Select(ModInfoRow.FromMod)
                .Cast<object>()
                .ToArray();
        }

        public string colony_summary()
        {
            if (Current.Game == null)
            {
                return "No game loaded.";
            }

            int colonists = PawnsFinder.AllMaps_FreeColonists.Count;
            int maps = Find.Maps != null ? Find.Maps.Count : 0;
            return "maps=" + maps + ", free_colonists=" + colonists;
        }

        public string[] list_saves()
        {
            return GenFilePaths.AllSavedGameFiles
                .OrderByDescending(file => file.LastWriteTimeUtc)
                .Select(file => file.Name)
                .ToArray();
        }

        public string latest_save_name()
        {
            FileInfo saveFile = GenFilePaths.AllSavedGameFiles
                .OrderByDescending(file => file.LastWriteTimeUtc)
                .FirstOrDefault();

            return saveFile != null ? saveFile.Name : "";
        }

        public string load_latest_save()
        {
            return PythonAutomation.LoadLatestSave();
        }

        public string load_save(string saveName)
        {
            return PythonAutomation.LoadSave(saveName);
        }

        public int thing_def_count()
        {
            return DefDatabase<ThingDef>.AllDefsListForReading.Count;
        }

        public string[] find_thing_defs(string query, int limit)
        {
            string needle = query ?? "";
            int cappedLimit = Math.Max(1, Math.Min(limit, 100));

            return DefDatabase<ThingDef>.AllDefsListForReading
                .Where(def =>
                    def.defName.IndexOf(needle, StringComparison.OrdinalIgnoreCase) >= 0 ||
                    (!string.IsNullOrEmpty(def.label) && def.label.IndexOf(needle, StringComparison.OrdinalIgnoreCase) >= 0))
                .Take(cappedLimit)
                .Select(def => def.defName + " (" + def.LabelCap.ToString() + ")")
                .ToArray();
        }

        public string spawn_near_selected(string thingDefName, int count)
        {
            if (Current.Game == null)
            {
                return "No game loaded.";
            }

            Map map = Find.CurrentMap;
            if (map == null)
            {
                return "No current map.";
            }

            ThingDef def = DefDatabase<ThingDef>.GetNamed(thingDefName, false);
            if (def == null)
            {
                return "ThingDef not found: " + thingDefName;
            }

            Thing selected = Find.Selector != null ? Find.Selector.SingleSelectedThing : null;
            IntVec3 center = selected != null && selected.Map == map ? selected.Position : map.Center;
            Thing thing = ThingMaker.MakeThing(def);
            thing.stackCount = Math.Max(1, Math.Min(count, def.stackLimit));

            bool placed = GenPlace.TryPlaceThing(thing, center, map, ThingPlaceMode.Near);
            return placed
                ? "Spawned " + thing.stackCount + "x " + def.defName + " near " + center
                : "Could not place " + def.defName + " near " + center;
        }
    }

    public sealed class ModInfoRow
    {
        public string name;
        public string packageId;
        public string rootDir;
        public string folderName;
        public bool isCoreMod;
        public bool isOfficialMod;

        public static ModInfoRow FromMod(ModContentPack mod)
        {
            return new ModInfoRow
            {
                name = mod.Name,
                packageId = mod.PackageId,
                rootDir = mod.RootDir,
                folderName = mod.FolderName,
                isCoreMod = mod.IsCoreMod,
                isOfficialMod = mod.IsOfficialMod
            };
        }
    }
}
