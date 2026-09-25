using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;
using UnityEngine.EventSystems;
using System.Linq;

namespace UnreliableProphecy
{
    /// <summary>
    /// Main Menu - Title + New Game / Continue / Load / Options / Quit.
    /// The UI is built at runtime (in case the scene has no wired UI elements),
    /// so the menu can never hard-crash on unassigned inspector references.
    /// </summary>
    public class MainMenuManager : MonoBehaviour
    {
        [Header("Optional inspector overrides (built at runtime if null)")]
        public GameObject mainPanel;
        public GameObject loadPanel;
        public GameObject optionsPanel;
        public GameObject quitConfirmPanel;
        public Button newGameButton;
        public Button continueButton;
        public Button loadButton;
        public Button optionsButton;
        public Button quitButton;
        public Transform saveSlotContainer;
        public GameObject saveSlotPrefab;
        public Button loadBackButton;
        public Button optionsBackButton;
        public Button quitYesButton;
        public Button quitNoButton;
        public Slider masterVolumeSlider;
        public Slider musicVolumeSlider;
        public Slider sfxVolumeSlider;
        public Toggle fullscreenToggle;
        public Dropdown qualityDropdown;

        private Canvas _canvas;

        void Start()
        {
            EnsureCanvasAndEvents();
            BuildAllUI();
            menuButtons = new Button[]{newGameButton, continueButton, loadButton, optionsButton, quitButton};
            selectedIndex = 0;
            UpdateSelection();
            Refresh();
            StartCoroutine(LogPositionsNextFrame());
        }

        System.Collections.IEnumerator LogPositionsNextFrame()
        {
            yield return null;
            yield return null;
            try {
                var cam = _canvas.worldCamera;
                Debug.Log($"[MainMenu] Canvas renderMode={_canvas.renderMode} cam={(cam?cam.name:"null")} scale={_canvas.scaleFactor}");
                void LogBtn(string n, Button b) {
                    if (b==null) { Debug.Log($"[MainMenu] {n} null"); return; }
                    var rt = b.GetComponent<RectTransform>();
                    var world = rt.position;
                    var screen = RectTransformUtility.WorldToScreenPoint(cam, world);
                    Debug.Log($"[MainMenu] {n} world {world} screen {screen} anchor {rt.anchoredPosition} rect {rt.rect}");
                }
                LogBtn("NewGame", newGameButton);
                LogBtn("Continue", continueButton);
                LogBtn("Load", loadButton);
                LogBtn("Options", optionsButton);
                LogBtn("Quit", quitButton);
            } catch (System.Exception e) { Debug.LogWarning("[MainMenu] LogPositions failed: " + e.Message); }
        }

        void EnsureCanvasAndEvents()
        {
            _canvas = FindAnyObjectByType<Canvas>();
            if (_canvas == null)
            {
                var go = new GameObject("UI Canvas");
                _canvas = go.AddComponent<Canvas>();
                go.AddComponent<CanvasScaler>();
                go.AddComponent<GraphicRaycaster>();
                Debug.Log("[MainMenu] Created new Canvas");
            }
            else
            {
                if (_canvas.GetComponent<CanvasScaler>() == null) _canvas.gameObject.AddComponent<CanvasScaler>();
                if (_canvas.GetComponent<GraphicRaycaster>() == null) _canvas.gameObject.AddComponent<GraphicRaycaster>();
                Debug.Log("[MainMenu] Reused existing Canvas: " + _canvas.name);
            }
            _canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            _canvas.gameObject.SetActive(true);
            Debug.Log("[MainMenu] Canvas ensured: " + _canvas.name);

            if (FindAnyObjectByType<EventSystem>() == null)
            {
                var es = new GameObject("EventSystem");
                es.AddComponent<EventSystem>();
                es.AddComponent<StandaloneInputModule>();
                Debug.Log("[MainMenu] Created EventSystem with StandaloneInputModule (activeInputHandler=Old)");
            }
            else Debug.Log("[MainMenu] EventSystem already exists: " + FindAnyObjectByType<EventSystem>().name);
        }

        int selectedIndex = 0;
        Button[] menuButtons;

        void Update()
        {
            if (Input.GetMouseButtonDown(0))
            {
                Debug.Log($"[MainMenu] Mouse click at {Input.mousePosition}");
                if (UnityEngine.EventSystems.EventSystem.current != null)
                {
                    var ped = new UnityEngine.EventSystems.PointerEventData(UnityEngine.EventSystems.EventSystem.current);
                    ped.position = Input.mousePosition;
                    var results = new System.Collections.Generic.List<UnityEngine.EventSystems.RaycastResult>();
                    UnityEngine.EventSystems.EventSystem.current.RaycastAll(ped, results);
                    Debug.Log($"[MainMenu] Raycast hits: {results.Count}");
                    for (int i=0;i<results.Count && i<3;i++) Debug.Log($"  hit {i}: {results[i].gameObject.name} depth {results[i].depth}");
                    if (results.Count==0) Debug.Log("[MainMenu] No UI hit - raycast failed");
                }
                else Debug.Log("[MainMenu] No EventSystem.current");
            }
            // Keyboard navigation for main menu (reliable fallback when mouse is finicky)
            if (mainPanel != null && mainPanel.activeSelf && menuButtons != null)
            {
                if (Input.GetKeyDown(KeyCode.DownArrow)) { selectedIndex = (selectedIndex+1)%menuButtons.Length; UpdateSelection(); }
                if (Input.GetKeyDown(KeyCode.UpArrow)) { selectedIndex = (selectedIndex-1+menuButtons.Length)%menuButtons.Length; UpdateSelection(); }
                if (Input.GetKeyDown(KeyCode.Space) || Input.GetKeyDown(KeyCode.Return) || Input.GetKeyDown(KeyCode.KeypadEnter))
                {
                    Debug.Log($"[MainMenu] Keyboard activate index {selectedIndex} ({menuButtons[selectedIndex].name})");
                    menuButtons[selectedIndex].onClick.Invoke();
                }
            }
            else if (Input.GetKeyDown(KeyCode.Escape))
            {
                if (loadPanel.activeSelf || optionsPanel.activeSelf || quitConfirmPanel.activeSelf) ShowMainPanel();
            }
        }

        void UpdateSelection()
        {
            if (menuButtons == null) return;
            for (int i=0;i<menuButtons.Length;i++)
            {
                if (menuButtons[i]==null) continue;
                var img = menuButtons[i].GetComponent<Image>();
                if (img) img.color = (i==selectedIndex) ? new Color(0.35f,0.42f,0.65f,1f) : new Color(0.22f,0.24f,0.32f,1f);
            }
            Debug.Log($"[MainMenu] Selected {selectedIndex}: {menuButtons[selectedIndex].name}");
        }

        Font _defaultFont;
        Font DefaultFont()
        {
            if (_defaultFont != null) return _defaultFont;
            _defaultFont = Resources.GetBuiltinResource<Font>("Arial.ttf");
            if (_defaultFont != null) return _defaultFont;
            string[] candidates = new string[] { "Arial", "DejaVu Sans", "Liberation Sans", "Noto Sans", "Lato", "FreeSans", "Sans" };
            foreach (var n in candidates)
            {
                try
                {
                    var f = Font.CreateDynamicFontFromOSFont(n, 14);
                    if (f != null && f.name != null) { _defaultFont = f; Debug.Log("[MainMenu] Using OS font: " + n); return _defaultFont; }
                }
                catch {}
            }
            try
            {
                var names = Font.GetOSInstalledFontNames();
                if (names != null && names.Length > 0)
                {
                    var f = Font.CreateDynamicFontFromOSFont(names[0], 14);
                    if (f != null) { _defaultFont = f; Debug.Log("[MainMenu] Using fallback font: " + names[0]); return _defaultFont; }
                }
            }
            catch {}
            Debug.LogWarning("[MainMenu] No font found, text will be invisible");
            return _defaultFont;
        }

        void BuildAllUI()
        {
            Debug.Log("[MainMenu] BuildAllUI start, canvas=" + (_canvas ? _canvas.name : "null"));
            mainPanel = NewPanel("MainPanel");
            loadPanel = NewPanel("LoadPanel");
            optionsPanel = NewPanel("OptionsPanel");
            quitConfirmPanel = NewPanel("QuitConfirmPanel");

            newGameButton = AddButton(mainPanel.transform, "New Game");
            continueButton = AddButton(mainPanel.transform, "Continue");
            loadButton = AddButton(mainPanel.transform, "Load");
            optionsButton = AddButton(mainPanel.transform, "Options");
            quitButton = AddButton(mainPanel.transform, "Quit");

            loadBackButton = AddButton(loadPanel.transform, "Back");
            saveSlotContainer = NewContainer(loadPanel.transform, "SaveSlotContainer");

            masterVolumeSlider = MakeSlider(optionsPanel.transform, "Master Volume");
            musicVolumeSlider = MakeSlider(optionsPanel.transform, "Music Volume");
            sfxVolumeSlider = MakeSlider(optionsPanel.transform, "SFX Volume");
            fullscreenToggle = MakeToggle(optionsPanel.transform, "Fullscreen");
            qualityDropdown = MakeDropdown(optionsPanel.transform, "Quality", QualitySettings.names.ToList());
            optionsBackButton = AddButton(optionsPanel.transform, "Back");

            quitYesButton = AddButton(quitConfirmPanel.transform, "Yes, Quit");
            quitNoButton = AddButton(quitConfirmPanel.transform, "No, Cancel");

            newGameButton?.onClick.AddListener(OnNewGame);
            continueButton?.onClick.AddListener(OnContinue);
            loadButton?.onClick.AddListener(ShowLoadPanel);
            optionsButton?.onClick.AddListener(ShowOptionsPanel);
            quitButton?.onClick.AddListener(ShowQuitConfirm);
            loadBackButton?.onClick.AddListener(ShowMainPanel);
            optionsBackButton?.onClick.AddListener(ShowMainPanel);
            quitYesButton?.onClick.AddListener(OnQuitYes);
            quitNoButton?.onClick.AddListener(ShowMainPanel);

            masterVolumeSlider?.onValueChanged.AddListener(OnMasterVolumeChanged);
            musicVolumeSlider?.onValueChanged.AddListener(OnMusicVolumeChanged);
            sfxVolumeSlider?.onValueChanged.AddListener(OnSFXVolumeChanged);
            fullscreenToggle?.onValueChanged.AddListener(OnFullscreenChanged);
            qualityDropdown?.onValueChanged.AddListener(OnQualityChanged);
            Debug.Log("[MainMenu] BuildAllUI done: mainPanel children=" + mainPanel.transform.childCount);
            try {
                Debug.Log($"[MainMenu] NewGame pos {newGameButton.GetComponent<RectTransform>().position} anchor {newGameButton.GetComponent<RectTransform>().anchoredPosition}");
                Debug.Log($"[MainMenu] Load pos {loadButton.GetComponent<RectTransform>().position} anchor {loadButton.GetComponent<RectTransform>().anchoredPosition}");
                Debug.Log($"[MainMenu] Options pos {optionsButton.GetComponent<RectTransform>().position} anchor {optionsButton.GetComponent<RectTransform>().anchoredPosition}");
            } catch {}
        }

        void Refresh()
        {
            ShowMainPanel();
            LoadOptions();
            PopulateSaveSlots();
            if (continueButton != null && SaveManager.Instance != null)
            {
                var slots = SaveManager.Instance.GetAllSaveSlots();
                continueButton.interactable = slots.Any(s => s.status != "Empty");
            }
        }

        // ---------------- handlers (unchanged behaviour) ----------------
        void OnNewGame()
        {
            Debug.Log("[MainMenu] New Game clicked, loading Quietvale");
            ResetGameState();
            SceneManager.LoadScene("Quietvale");
        }

        void OnContinue()
        {
            if (SaveManager.Instance == null) return;
            var save = SaveManager.Instance.LoadGame(0);
            if (save != null)
            {
                SaveManager.Instance.ApplySaveData(save);
                SceneManager.LoadScene(save.region);
            }
        }

        void ShowLoadPanel()
        {
            Debug.Log("[MainMenu] ShowLoadPanel");
            mainPanel.SetActive(false);
            loadPanel.SetActive(true);
            PopulateSaveSlots();
        }

        void ShowOptionsPanel()
        {
            Debug.Log("[MainMenu] ShowOptionsPanel");
            mainPanel.SetActive(false);
            optionsPanel.SetActive(true);
        }

        void ShowQuitConfirm()
        {
            Debug.Log("[MainMenu] ShowQuitConfirm");
            mainPanel.SetActive(false);
            quitConfirmPanel.SetActive(true);
        }

        void ShowMainPanel()
        {
            Debug.Log("[MainMenu] ShowMainPanel");
            mainPanel.SetActive(true);
            loadPanel.SetActive(false);
            optionsPanel.SetActive(false);
            quitConfirmPanel.SetActive(false);
        }

        void OnQuitYes()
        {
            Debug.Log("[MainMenu] Quit Yes");
#if UNITY_EDITOR
            UnityEditor.EditorApplication.isPlaying = false;
#else
            Application.Quit();
#endif
        }

        void PopulateSaveSlots()
        {
            if (saveSlotContainer == null) return;
            foreach (Transform child in saveSlotContainer)
                Destroy(child.gameObject);

            var slots = SaveManager.Instance != null ? SaveManager.Instance.GetAllSaveSlots() : null;
            if (slots == null) return;
            for (int i = 0; i < slots.Length; i++)
            {
                int slotIndex = i;
                var data = slots[i];
                var row = new GameObject("Slot" + i);
                row.transform.SetParent(saveSlotContainer, false);
                var rt = row.AddComponent<RectTransform>();
                rt.sizeDelta = new Vector2(460, 44);
                var leRow = row.AddComponent<LayoutElement>();
                leRow.preferredHeight = 44; leRow.preferredWidth = 460;

                var img = row.AddComponent<Image>();
                img.color = new Color(0.18f, 0.18f, 0.22f, 1f);
                var btn = row.AddComponent<Button>();
                btn.targetGraphic = img;

                var txt = new GameObject("Text");
                txt.transform.SetParent(row.transform, false);
                var t = txt.AddComponent<Text>();
                t.color = Color.white; t.font = DefaultFont(); t.fontSize = 14;
                t.alignment = TextAnchor.MiddleLeft;
                t.text = data.status != "Empty"
                    ? $"Slot {i + 1}: {data.region}  ({data.timestamp})"
                    : $"Slot {i + 1}: Empty – Awaiting Documentation.";
                var tRT = t.GetComponent<RectTransform>();
                tRT.anchorMin = Vector2.zero; tRT.anchorMax = Vector2.one;
                tRT.offsetMin = new Vector2(10, 0); tRT.offsetMax = Vector2.zero;

                btn.interactable = data.status != "Empty";
                btn.onClick.AddListener(() => LoadSlot(slotIndex));
            }
        }

        void LoadSlot(int slotIndex)
        {
            if (SaveManager.Instance == null) return;
            var save = SaveManager.Instance.LoadGame(slotIndex);
            if (save != null)
            {
                SaveManager.Instance.ApplySaveData(save);
                SceneManager.LoadScene(save.region);
            }
        }

        void ResetGameState()
        {
            QuestManager.Instance?.Reset();
            SaveManager.Instance?.Reset();
            InventoryManager.Instance?.Reset();
            BinderManager.Instance?.Reset();
            CompanionManager.Instance?.Reset();
        }

        void LoadOptions()
        {
            if (masterVolumeSlider) masterVolumeSlider.value = PlayerPrefs.GetFloat("MasterVolume", 1f);
            if (musicVolumeSlider) musicVolumeSlider.value = PlayerPrefs.GetFloat("MusicVolume", 0.8f);
            if (sfxVolumeSlider) sfxVolumeSlider.value = PlayerPrefs.GetFloat("SFXVolume", 1f);
            if (fullscreenToggle) fullscreenToggle.isOn = Screen.fullScreen;
            if (qualityDropdown) qualityDropdown.value = QualitySettings.GetQualityLevel();
        }

        public void OnMasterVolumeChanged(float value)
        {
            AudioListener.volume = value;
            PlayerPrefs.SetFloat("MasterVolume", value);
        }

        public void OnMusicVolumeChanged(float value)
        {
            PlayerPrefs.SetFloat("MusicVolume", value);
        }

        public void OnSFXVolumeChanged(float value)
        {
            PlayerPrefs.SetFloat("SFXVolume", value);
        }

        public void OnFullscreenChanged(bool value)
        {
            Screen.fullScreen = value;
        }

        public void OnQualityChanged(int value)
        {
            QualitySettings.SetQualityLevel(value);
        }

        // ---------------- UI construction helpers ----------------
        GameObject NewPanel(string name)
        {
            var go = new GameObject(name);
            go.transform.SetParent(_canvas.transform, false);
            var rt = go.AddComponent<RectTransform>();
            rt.anchorMin = Vector2.zero; rt.anchorMax = Vector2.one;
            rt.offsetMin = Vector2.zero; rt.offsetMax = Vector2.zero;
            var img = go.AddComponent<Image>();
            img.color = new Color(0.08f, 0.08f, 0.12f, 0.96f);
            var vlg = go.AddComponent<VerticalLayoutGroup>();
            vlg.spacing = 12; vlg.padding = new RectOffset(40, 40, 60, 60);
            vlg.childAlignment = TextAnchor.MiddleCenter;
            vlg.childForceExpandWidth = false; vlg.childForceExpandHeight = false;
            go.SetActive(false);
            return go;
        }

        Transform NewContainer(Transform parent, string name)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            var rt = go.AddComponent<RectTransform>();
            rt.anchorMin = new Vector2(0, 0); rt.anchorMax = new Vector2(1, 1);
            rt.offsetMin = Vector2.zero; rt.offsetMax = Vector2.zero;
            var vlg = go.AddComponent<VerticalLayoutGroup>();
            vlg.spacing = 6; vlg.childAlignment = TextAnchor.UpperCenter;
            vlg.childForceExpandWidth = false; vlg.childForceExpandHeight = false;
            return go.transform;
        }

        Button AddButton(Transform parent, string label)
        {
            var go = new GameObject(label);
            go.transform.SetParent(parent, false);
            var rt = go.AddComponent<RectTransform>();
            rt.sizeDelta = new Vector2(320, 52);
            var le = go.AddComponent<LayoutElement>();
            le.preferredHeight = 52; le.preferredWidth = 320; le.minHeight = 52;
            var img = go.AddComponent<Image>();
            img.color = new Color(0.22f, 0.24f, 0.32f, 1f);
            var txt = new GameObject("Text");
            txt.transform.SetParent(go.transform, false);
            var t = txt.AddComponent<Text>();
            t.text = label; t.alignment = TextAnchor.MiddleCenter;
            t.color = Color.white; t.fontSize = 24; t.font = DefaultFont();
            var tRT = t.GetComponent<RectTransform>();
            tRT.anchorMin = Vector2.zero; tRT.anchorMax = Vector2.one;
            tRT.offsetMin = Vector2.zero; tRT.offsetMax = Vector2.zero;
            var btn = go.AddComponent<Button>();
            btn.targetGraphic = img;
            return btn;
        }

        Slider MakeSlider(Transform parent, string label)
        {
            var go = new GameObject(label);
            go.transform.SetParent(parent, false);
            var rt = go.AddComponent<RectTransform>();
            rt.sizeDelta = new Vector2(360, 36);
            var le2 = go.AddComponent<LayoutElement>();
            le2.preferredHeight = 44; le2.preferredWidth = 360;
            var labelTxt = new GameObject("Label");
            labelTxt.transform.SetParent(go.transform, false);
            var lt = labelTxt.AddComponent<Text>(); lt.text = label; lt.color = Color.white; lt.font = DefaultFont(); lt.fontSize = 14; lt.alignment = TextAnchor.MiddleLeft;
            var ltRT = labelTxt.GetComponent<RectTransform>();
            ltRT.anchorMin = new Vector2(0, 0.65f); ltRT.anchorMax = new Vector2(1, 1); ltRT.offsetMin = new Vector2(5,0); ltRT.offsetMax = Vector2.zero;
            var bg = new GameObject("Background");
            bg.transform.SetParent(go.transform, false);
            var bgImg = bg.AddComponent<Image>(); bgImg.color = new Color(0.3f, 0.3f, 0.3f, 1f);
            var bgRT = bg.GetComponent<RectTransform>();
            bgRT.anchorMin = new Vector2(0, 0.08f); bgRT.anchorMax = new Vector2(1, 0.45f);
            bgRT.offsetMin = Vector2.zero; bgRT.offsetMax = Vector2.zero;
            var fill = new GameObject("Fill");
            fill.transform.SetParent(go.transform, false);
            var fillImg = fill.AddComponent<Image>(); fillImg.color = new Color(0.4f, 0.7f, 1f, 1f);
            var fillRT = fill.GetComponent<RectTransform>();
            fillRT.anchorMin = new Vector2(0, 0.08f); fillRT.anchorMax = new Vector2(1, 0.45f);
            fillRT.offsetMin = Vector2.zero; fillRT.offsetMax = Vector2.zero;
            var handle = new GameObject("Handle");
            handle.transform.SetParent(go.transform, false);
            var handleImg = handle.AddComponent<Image>(); handleImg.color = Color.white;
            var handleRT = handle.GetComponent<RectTransform>();
            handleRT.sizeDelta = new Vector2(20, 28);
            var slider = go.AddComponent<Slider>();
            slider.fillRect = fill.GetComponent<RectTransform>();
            slider.handleRect = handle.GetComponent<RectTransform>();
            slider.targetGraphic = handleImg;
            slider.value = 1f;
            return slider;
        }

        Toggle MakeToggle(Transform parent, string label)
        {
            var go = new GameObject(label);
            go.transform.SetParent(parent, false);
            var rt = go.AddComponent<RectTransform>();
            rt.sizeDelta = new Vector2(360, 36);
            var le3 = go.AddComponent<LayoutElement>();
            le3.preferredHeight = 36; le3.preferredWidth = 360;
            var bg = new GameObject("Background");
            bg.transform.SetParent(go.transform, false);
            var bgImg = bg.AddComponent<Image>(); bgImg.color = new Color(0.3f, 0.3f, 0.3f, 1f);
            var bgRT = bg.GetComponent<RectTransform>();
            bgRT.sizeDelta = new Vector2(32, 32);
            bgRT.anchorMin = new Vector2(0, 0.5f); bgRT.anchorMax = new Vector2(0, 0.5f);
            bgRT.anchoredPosition = new Vector2(18, 0);
            var check = new GameObject("Checkmark");
            check.transform.SetParent(bg.transform, false);
            var chkImg = check.AddComponent<Image>(); chkImg.color = Color.white;
            var chkRT = check.GetComponent<RectTransform>();
            chkRT.sizeDelta = new Vector2(20, 20);
            var labelTxt = new GameObject("Label");
            labelTxt.transform.SetParent(go.transform, false);
            var lt = labelTxt.AddComponent<Text>(); lt.text = label; lt.color = Color.white; lt.font = DefaultFont(); lt.fontSize = 18;
            var ltRT = labelTxt.GetComponent<RectTransform>();
            ltRT.anchorMin = new Vector2(0.15f, 0); ltRT.anchorMax = new Vector2(1, 1);
            ltRT.offsetMin = Vector2.zero; ltRT.offsetMax = Vector2.zero;
            var tog = go.AddComponent<Toggle>();
            tog.targetGraphic = bgImg; tog.graphic = chkImg;
            return tog;
        }

        Dropdown MakeDropdown(Transform parent, string label, System.Collections.Generic.List<string> opts)
        {
            var go = new GameObject(label);
            go.transform.SetParent(parent, false);
            var rt = go.AddComponent<RectTransform>();
            rt.sizeDelta = new Vector2(360, 36);
            var le4 = go.AddComponent<LayoutElement>();
            le4.preferredHeight = 36; le4.preferredWidth = 360;
            var bg = go.AddComponent<Image>(); bg.color = new Color(0.3f, 0.3f, 0.3f, 1f);
            var labelTxt = new GameObject("Label");
            labelTxt.transform.SetParent(go.transform, false);
            var lt = labelTxt.AddComponent<Text>(); lt.text = label; lt.color = Color.white; lt.font = DefaultFont(); lt.fontSize = 18;
            var ltRT = labelTxt.GetComponent<RectTransform>();
            ltRT.anchorMin = new Vector2(0.05f, 0); ltRT.anchorMax = new Vector2(0.95f, 1);
            ltRT.offsetMin = Vector2.zero; ltRT.offsetMax = Vector2.zero;
            var dd = go.AddComponent<Dropdown>();
            dd.captionText = lt;
            dd.AddOptions(opts);
            var arrow = new GameObject("Arrow");
            arrow.transform.SetParent(go.transform, false);
            var at = arrow.AddComponent<Text>(); at.text = "v"; at.color = Color.white; at.font = DefaultFont(); at.fontSize = 18; at.alignment = TextAnchor.MiddleCenter;
            var atRT = at.GetComponent<RectTransform>();
            atRT.anchorMin = new Vector2(0.85f, 0); atRT.anchorMax = new Vector2(1, 1); atRT.offsetMin = Vector2.zero; atRT.offsetMax = Vector2.zero;
            var template = new GameObject("Template");
            template.transform.SetParent(go.transform, false);
            var tRT = template.AddComponent<RectTransform>();
            tRT.anchorMin = new Vector2(0,0); tRT.anchorMax = new Vector2(1,0); tRT.anchoredPosition = new Vector2(0, -40); tRT.sizeDelta = new Vector2(0,150);
            template.AddComponent<Image>().color = new Color(0.15f,0.15f,0.18f,1);
            template.SetActive(false);
            dd.template = tRT;
            return dd;
        }
    }
}
