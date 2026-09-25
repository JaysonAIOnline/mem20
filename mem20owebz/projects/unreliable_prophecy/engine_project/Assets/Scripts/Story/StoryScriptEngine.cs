using UnityEngine;
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;

namespace UnreliableProphecy
{
    /// <summary>
    /// Story Script Engine - manages scripted quest events, main storyline sequences,
    /// and progression triggers. Coordinates with QuestManager, CutsceneManager,
    /// and DialogueManager to drive the narrative forward.
    /// </summary>
    public class StoryScriptEngine : MonoBehaviour
    {
        public static StoryScriptEngine Instance { get; private set; }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void EnsureExists()
        {
            if (Instance == null)
            {
                var go = new GameObject(typeof(StoryScriptEngine).Name);
                Instance = go.AddComponent<StoryScriptEngine>();
            }
        }

        [Header("Story Settings")]
        public List<StoryChapter> chapters = new List<StoryChapter>();
        public bool autoStartChapterOnRegionEnter = true;

        // State
        private StoryChapter activeChapter;
        private int currentSequenceIndex;
        private bool isSequenceActive;
        private Dictionary<string, bool> storyFlags = new Dictionary<string, bool>();

        // Events
        public event Action<StoryChapter> OnChapterStarted;
        public event Action<StoryChapter> OnChapterCompleted;
        public event Action<StorySequence> OnSequenceStarted;
        public event Action<StorySequence> OnSequenceCompleted;
        public event Action<string> OnStoryFlagSet;

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);

            InitializeChapters();
        }

        void Start()
        {
            // Subscribe to region transitions
            var saveManager = FindObjectOfType<SaveManager>();
            // Auto-start first chapter if none active
            if (activeChapter == null && chapters.Count > 0)
            {
                StartChapter(chapters[0].chapterId);
            }
        }

        /// <summary>
        /// Creates the default chapter structure based on the production package story outline.
        /// </summary>
        private void InitializeChapters()
        {
            if (chapters.Count > 0) return; // Already populated

            // Chapter 1: Ordinary Life (Quietvale Tutorial)
            chapters.Add(new StoryChapter
            {
                chapterId = "CH1",
                chapterNumber = 1,
                name = "Ordinary Life",
                description = "The Bureaucrat arrives with Prophecy 47-B (Revised). The player must sign forms and learn the basics.",
                regionId = "R1",
                sequences = new List<StorySequence>
                {
                    new StorySequence
                    {
                        sequenceId = "CH1_SEQ1",
                        name = "The Prophecy Arrives",
                        description = "The Bureaucrat delivers the prophecy to the player's home.",
                        triggerType = SequenceTriggerType.OnRegionEnter,
                        triggerData = "R1",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.PlayCutscene,
                                parameter = "cutscene_prophecy_arrival",
                                delay = 0f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.AcceptQuest,
                                parameter = "T01",
                                delay = 1f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.DisplayNarration,
                                parameter = "You are now the Chosen One. Please sign here, here, and initial here.",
                                delay = 2f
                            }
                        }
                    },
                    new StorySequence
                    {
                        sequenceId = "CH1_SEQ2",
                        name = "The First Filing",
                        description = "Player completes the tutorial quest - filing their first form.",
                        triggerType = SequenceTriggerType.OnQuestCompleted,
                        triggerData = "T01",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.DisplayNarration,
                                parameter = "The Prophecy Binder feels heavier than it looks. Inside, words shift and rearrange themselves.",
                                delay = 0.5f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.AcceptQuest,
                                parameter = "T02",
                                delay = 1f
                            }
                        }
                    },
                    new StorySequence
                    {
                        sequenceId = "CH1_SEQ3",
                        name = "Ink & Parchment",
                        description = "Player gathers supplies for the journey ahead.",
                        triggerType = SequenceTriggerType.OnQuestCompleted,
                        triggerData = "T02",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.PlayCutscene,
                                parameter = "cutscene_wizard_arrival",
                                delay = 0f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.SetStoryFlag,
                                parameter = "met_wizard",
                                delay = 1f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.DisplayNarration,
                                parameter = "An old wizard appears from behind a filing cabinet. 'I'll be your companion. Try not to lose the paperwork.'",
                                delay = 2f
                            }
                        }
                    },
                    new StorySequence
                    {
                        sequenceId = "CH1_SEQ4",
                        name = "Tutorial Woods",
                        description = "Player fights their first enemy and leaves Quietvale.",
                        triggerType = SequenceTriggerType.OnRegionEnter,
                        triggerData = "QV-WOODS",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.SpawnEnemy,
                                parameter = "CR_MisfiledSkeleton",
                                delay = 0f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.DisplayNarration,
                                parameter = "A skeleton lurches toward you. It appears to have been misfiled. Defend yourself!",
                                delay = 1f
                            }
                        }
                    },
                    new StorySequence
                    {
                        sequenceId = "CH1_SEQ5",
                        name = "Leaving Quietvale",
                        description = "Player exits Quietvale and enters Bureaucracy Hills.",
                        triggerType = SequenceTriggerType.OnRegionTransition,
                        triggerData = "QV-GATE",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.PlayCutscene,
                                parameter = "cutscene_leave_quietvale",
                                delay = 0f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.CompleteChapter,
                                parameter = "CH1",
                                delay = 3f
                            }
                        }
                    }
                }
            });

            // Chapter 2: Leaving Home
            chapters.Add(new StoryChapter
            {
                chapterId = "CH2",
                chapterNumber = 2,
                name = "Leaving Home",
                description = "The player travels to Bureaucracy Hills and begins their first major bureaucratic challenge.",
                regionId = "R2",
                sequences = new List<StorySequence>
                {
                    new StorySequence
                    {
                        sequenceId = "CH2_SEQ1",
                        name = "Entering Bureaucracy Hills",
                        description = "The player arrives at the Hills and encounters the Permit Office.",
                        triggerType = SequenceTriggerType.OnRegionEnter,
                        triggerData = "R2",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.DisplayNarration,
                                parameter = "Bureaucracy Hills stretches before you. Filing cabinets line the paths like tombstones.",
                                delay = 1f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.AcceptQuest,
                                parameter = "M01",
                                delay = 2f
                            }
                        }
                    },
                    new StorySequence
                    {
                        sequenceId = "CH2_SEQ2",
                        name = "The Lost Ledger",
                        description = "The player discovers the Archivist's side quest.",
                        triggerType = SequenceTriggerType.OnWaypointReached,
                        triggerData = "WP-BH-06",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.AcceptQuest,
                                parameter = "S01",
                                delay = 0.5f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.DisplayNarration,
                                parameter = "The Archivist looks up from a mountain of papers. 'Three ledger pages have gone missing. The entire region is out of balance until they're found.'",
                                delay = 1f
                            }
                        }
                    },
                    new StorySequence
                    {
                        sequenceId = "CH2_SEQ3",
                        name = "The Misplaced Amendment",
                        description = "The player finds Amendment #1 and the quest rules change.",
                        triggerType = SequenceTriggerType.OnQuestCompleted,
                        triggerData = "M01",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.PlayCutscene,
                                parameter = "cutscene_first_amendment",
                                delay = 0f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.AcceptQuest,
                                parameter = "M02",
                                delay = 2f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.SetStoryFlag,
                                parameter = "found_amendment_1",
                                delay = 2.5f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.DisplayNarration,
                                parameter = "The Amendment glows softly: 'Section 47-B is hereby revised to add: All prophecies must be filed in triplicate.'",
                                delay = 3f
                            }
                        }
                    },
                    new StorySequence
                    {
                        sequenceId = "CH2_SEQ4",
                        name = "Final Stamp",
                        description = "The player completes Bureaucracy Hills.",
                        triggerType = SequenceTriggerType.OnQuestCompleted,
                        triggerData = "M02",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.AcceptQuest,
                                parameter = "M03",
                                delay = 0.5f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.DisplayNarration,
                                parameter = "The Magistrate hands you the Grand Stamp. 'Well done. The Forest of Unhelpful Trees awaits.'",
                                delay = 1f
                            }
                        }
                    },
                    new StorySequence
                    {
                        sequenceId = "CH2_SEQ5",
                        name = "Exit Bureaucracy Hills",
                        description = "The player transitions to the Forest.",
                        triggerType = SequenceTriggerType.OnRegionTransition,
                        triggerData = "BH-GATE",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.CompleteChapter,
                                parameter = "CH2",
                                delay = 0f
                            }
                        }
                    }
                }
            });

            // Chapter 3: The Forest of Unhelpful Trees
            chapters.Add(new StoryChapter
            {
                chapterId = "CH3",
                chapterNumber = 3,
                name = "The Unhelpful Forest",
                description = "The player navigates the Forest of Unhelpful Trees, where the flora has opinions.",
                regionId = "R3",
                sequences = new List<StorySequence>
                {
                    new StorySequence
                    {
                        sequenceId = "CH3_SEQ1",
                        name = "Forest Entry",
                        description = "The player enters the forest and encounters the Talking Tree.",
                        triggerType = SequenceTriggerType.OnRegionEnter,
                        triggerData = "R3",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.DisplayNarration,
                                parameter = "The trees here are passive-aggressive. One of them clears its throat as you pass.",
                                delay = 1f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.AcceptQuest,
                                parameter = "M04",
                                delay = 2f
                            }
                        }
                    },
                    new StorySequence
                    {
                        sequenceId = "CH3_SEQ2",
                        name = "The Talking Tree's Riddle",
                        description = "The Talking Tree challenges the player with a bureaucratic riddle.",
                        triggerType = SequenceTriggerType.OnWaypointReached,
                        triggerData = "WP-FR-03",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.DisplayNarration,
                                parameter = "'I used to be a memo,' the tree rustles. 'Now I'm furniture. Life is full of disappointments. Answer my riddle to pass.'",
                                delay = 1f
                            }
                        }
                    },
                    new StorySequence
                    {
                        sequenceId = "CH3_SEQ3",
                        name = "Forest Depths",
                        description = "The player reaches the deep forest and finds the exit.",
                        triggerType = SequenceTriggerType.OnWaypointReached,
                        triggerData = "WP-FR-06",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.CompleteChapter,
                                parameter = "CH3",
                                delay = 0f
                            }
                        }
                    }
                }
            });

            // Chapter 4: Gathering the Party
            chapters.Add(new StoryChapter
            {
                chapterId = "CH4",
                chapterNumber = 4,
                name = "Gathering the Unwilling",
                description = "The player arrives at the City of Forms and begins recruiting companions.",
                regionId = "R4",
                sequences = new List<StorySequence>
                {
                    new StorySequence
                    {
                        sequenceId = "CH4_SEQ1",
                        name = "City of Forms",
                        description = "The player enters the bureaucratic hub of the world.",
                        triggerType = SequenceTriggerType.OnRegionEnter,
                        triggerData = "R4",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.PlayCutscene,
                                parameter = "cutscene_city_arrival",
                                delay = 0f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.DisplayNarration,
                                parameter = "The City of Forms stretches in concentric rings. Every window has a queue. Every queue has a forms office. Every forms office has a longer queue.",
                                delay = 2f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.AcceptQuest,
                                parameter = "M05",
                                delay = 3f
                            }
                        }
                    },
                    new StorySequence
                    {
                        sequenceId = "CH4_SEQ2",
                        name = "Department of Previous Failures",
                        description = "The player visits the memorial department.",
                        triggerType = SequenceTriggerType.OnWaypointReached,
                        triggerData = "WP-CT-04",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.DisplayNarration,
                                parameter = "The Department of Previous Failures is quiet. Rows of plaques honor Chosen Ones who didn't make it. The list is long.",
                                delay = 1f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.SetStoryFlag,
                                parameter = "visited_previous_failures",
                                delay = 2f
                            }
                        }
                    },
                    new StorySequence
                    {
                        sequenceId = "CH4_SEQ3",
                        name = "Party Assembled",
                        description = "The player has recruited enough companions.",
                        triggerType = SequenceTriggerType.OnQuestCompleted,
                        triggerData = "M05",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.PlayCutscene,
                                parameter = "cutscene_party_assembled",
                                delay = 0f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.CompleteChapter,
                                parameter = "CH4",
                                delay = 5f
                            }
                        }
                    }
                }
            });

            // Chapter 5: The Overflow Archives
            chapters.Add(new StoryChapter
            {
                chapterId = "CH5",
                chapterNumber = 5,
                name = "Weight of Precedence",
                description = "The player explores the Overflow Archives and confronts the Paper Elemental.",
                regionId = "R5",
                sequences = new List<StorySequence>
                {
                    new StorySequence
                    {
                        sequenceId = "CH5_SEQ1",
                        name = "Entering the Archives",
                        description = "The player enters the Overflow Archives.",
                        triggerType = SequenceTriggerType.OnRegionEnter,
                        triggerData = "R5",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.DisplayNarration,
                                parameter = "The Overflow Archives smell of old paper and forgotten purposes. Something stirs in the deep stacks.",
                                delay = 1f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.AcceptQuest,
                                parameter = "M06",
                                delay = 2f
                            }
                        }
                    },
                    new StorySequence
                    {
                        sequenceId = "CH5_SEQ2",
                        name = "The Quiet Reading Room",
                        description = "The player finds the hidden memo.",
                        triggerType = SequenceTriggerType.OnWaypointReached,
                        triggerData = "WP-OA-05",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.DisplayNarration,
                                parameter = "Tucked behind a misfiled book, you find a memo: 'To whom it may concern: Prophecy 47-C is in draft. Recommend immediate revision of 47-B before things get worse.'",
                                delay = 1f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.SetStoryFlag,
                                parameter = "found_47c_memo",
                                delay = 2f
                            }
                        }
                    },
                    new StorySequence
                    {
                        sequenceId = "CH5_SEQ3",
                        name = "Paper Elemental Boss",
                        description = "The player confronts the Paper Elemental.",
                        triggerType = SequenceTriggerType.OnWaypointReached,
                        triggerData = "WP-OA-04",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.PlayCutscene,
                                parameter = "cutscene_paper_elemental",
                                delay = 0f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.SpawnEnemy,
                                parameter = "CR_PaperElemental",
                                delay = 2f
                            }
                        }
                    },
                    new StorySequence
                    {
                        sequenceId = "CH5_SEQ4",
                        name = "Archives Cleared",
                        description = "The Paper Elemental is defeated.",
                        triggerType = SequenceTriggerType.OnQuestCompleted,
                        triggerData = "M06",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.CompleteChapter,
                                parameter = "CH5",
                                delay = 0f
                            }
                        }
                    }
                }
            });

            // Chapter 6: Ruins of Previous Chosen Ones
            chapters.Add(new StoryChapter
            {
                chapterId = "CH6",
                chapterNumber = 6,
                name = "Weight of Precedence",
                description = "The player visits the melancholy memorial to previous Chosen Ones.",
                regionId = "R6",
                sequences = new List<StorySequence>
                {
                    new StorySequence
                    {
                        sequenceId = "CH6_SEQ1",
                        name = "The Memorial",
                        description = "The player enters the Ruins and reflects on the previous Chosen Ones.",
                        triggerType = SequenceTriggerType.OnRegionEnter,
                        triggerData = "R6",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.PlayCutscene,
                                parameter = "cutscene_ruins_arrival",
                                delay = 0f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.DisplayNarration,
                                parameter = "The statues of previous Chosen Ones line the path. Their faces show determination, fear, and in one case, mild annoyance. The bureaucracy got them all.",
                                delay = 3f
                            }
                        }
                    },
                    new StorySequence
                    {
                        sequenceId = "CH6_SEQ2",
                        name = "The Final Statue",
                        description = "The player finds the statue of the most recent Chosen One.",
                        triggerType = SequenceTriggerType.OnWaypointReached,
                        triggerData = "WP-RU-02",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.DisplayNarration,
                                parameter = "The last statue holds a plaque: 'Here stood Chosen One #347. Lost due to incomplete paperwork. May their amendments be forever pending.'",
                                delay = 1f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.SetStoryFlag,
                                parameter = "learned_previous_chosen",
                                delay = 2f
                            }
                        }
                    },
                    new StorySequence
                    {
                        sequenceId = "CH6_SEQ3",
                        name = "Exit to Final Zone",
                        description = "The player leaves for the Final Administrative Zone.",
                        triggerType = SequenceTriggerType.OnRegionTransition,
                        triggerData = "RU-GATE",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.CompleteChapter,
                                parameter = "CH6",
                                delay = 0f
                            }
                        }
                    }
                }
            });

            // Chapter 7: Final Administrative Zone
            chapters.Add(new StoryChapter
            {
                chapterId = "CH7",
                chapterNumber = 7,
                name = "The Final Review",
                description = "The player confronts the Desk of Absolute Authority and chooses their ending.",
                regionId = "R7",
                sequences = new List<StorySequence>
                {
                    new StorySequence
                    {
                        sequenceId = "CH7_SEQ1",
                        name = "The Final Corridor",
                        description = "The player enters the Final Administrative Zone.",
                        triggerType = SequenceTriggerType.OnRegionEnter,
                        triggerData = "R7",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.PlayCutscene,
                                parameter = "cutscene_final_zone_arrival",
                                delay = 0f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.DisplayNarration,
                                parameter = "The Desk of Absolute Authority looms ahead. Three departments watch from their zones. The Bureaucrat stands waiting.",
                                delay = 3f
                            }
                        }
                    },
                    new StorySequence
                    {
                        sequenceId = "CH7_SEQ2",
                        name = "The Final Boss",
                        description = "The player confronts the Desk of Absolute Authority.",
                        triggerType = SequenceTriggerType.OnWaypointReached,
                        triggerData = "WP-FA-02",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.PlayCutscene,
                                parameter = "cutscene_final_boss",
                                delay = 0f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.SpawnEnemy,
                                parameter = "CR_FinalBoss",
                                delay = 3f
                            }
                        }
                    },
                    new StorySequence
                    {
                        sequenceId = "CH7_SEQ3",
                        name = "The Choice",
                        description = "The player chooses to sign or refuse the final form.",
                        triggerType = SequenceTriggerType.OnQuestCompleted,
                        triggerData = "M07",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.PlayCutscene,
                                parameter = "cutscene_ending_choice",
                                delay = 0f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.DisplayNarration,
                                parameter = "The form lies before you. Sign, and the prophecy is fulfilled. Refuse, and... well, there's always Form 47-C.",
                                delay = 3f
                            }
                        }
                    },
                    new StorySequence
                    {
                        sequenceId = "CH7_SEQ4",
                        name = "Epilogue",
                        description = "The game concludes with certificates and bureaucracy continuing.",
                        triggerType = SequenceTriggerType.OnStoryFlagSet,
                        triggerData = "ending_chosen",
                        events = new List<StoryEvent>
                        {
                            new StoryEvent
                            {
                                eventType = StoryEventType.PlayCutscene,
                                parameter = "cutscene_epilogue",
                                delay = 0f
                            },
                            new StoryEvent
                            {
                                eventType = StoryEventType.CompleteChapter,
                                parameter = "CH7",
                                delay = 10f
                            }
                        }
                    }
                }
            });
        }

        public void StartChapter(string chapterId)
        {
            var chapter = chapters.FirstOrDefault(c => c.chapterId == chapterId);
            if (chapter == null) return;

            activeChapter = chapter;
            currentSequenceIndex = 0;
            OnChapterStarted?.Invoke(chapter);

            Debug.Log($"[StoryScriptEngine] Started chapter: {chapter.name}");
        }

        public void CompleteChapter(string chapterId)
        {
            if (activeChapter != null && activeChapter.chapterId == chapterId)
            {
                OnChapterCompleted?.Invoke(activeChapter);
                Debug.Log($"[StoryScriptEngine] Completed chapter: {activeChapter.name}");

                // Auto-start next chapter
                int nextIndex = chapters.IndexOf(activeChapter) + 1;
                if (nextIndex < chapters.Count)
                {
                    StartChapter(chapters[nextIndex].chapterId);
                }
            }
        }

        public void TriggerSequence(string sequenceId)
        {
            if (activeChapter == null) return;

            var sequence = activeChapter.sequences.FirstOrDefault(s => s.sequenceId == sequenceId);
            if (sequence == null) return;

            StartCoroutine(ExecuteSequence(sequence));
        }

        private IEnumerator ExecuteSequence(StorySequence sequence)
        {
            isSequenceActive = true;
            OnSequenceStarted?.Invoke(sequence);

            Debug.Log($"[StoryScriptEngine] Executing sequence: {sequence.name}");

            foreach (var evt in sequence.events)
            {
                if (evt.delay > 0)
                {
                    yield return new WaitForSeconds(evt.delay);
                }

                ExecuteEvent(evt);
            }

            OnSequenceCompleted?.Invoke(sequence);
            isSequenceActive = false;
        }

        private void ExecuteEvent(StoryEvent evt)
        {
            switch (evt.eventType)
            {
                case StoryEventType.PlayCutscene:
                    var cm = CutsceneManager.Instance;
                    if (cm != null) cm.PlayCutscene(evt.parameter);
                    break;

                case StoryEventType.AcceptQuest:
                    var qm = QuestManager.Instance;
                    if (qm != null) qm.AcceptQuest(evt.parameter);
                    break;

                case StoryEventType.CompleteQuest:
                    var qm2 = QuestManager.Instance;
                    if (qm2 != null)
                    {
                        var quest = qm2.GetQuest(evt.parameter);
                        if (quest != null)
                        {
                            quest.status = QuestStatus.Completed;
                            qm2.OnQuestCompleted?.Invoke(quest);
                        }
                    }
                    break;

                case StoryEventType.UpdateQuest:
                    var qm3 = QuestManager.Instance;
                    if (qm3 != null)
                    {
                        // parameter format: "questId|objectiveDescription"
                        var parts = evt.parameter.Split('|');
                        if (parts.Length == 2)
                        {
                            qm3.UpdateObjective(parts[0], parts[1]);
                        }
                    }
                    break;

                case StoryEventType.DisplayNarration:
                    Debug.Log($"[Narration] {evt.parameter}");
                    // TODO: Display in UI
                    break;

                case StoryEventType.SetStoryFlag:
                    SetStoryFlag(evt.parameter, true);
                    break;

                case StoryEventType.SpawnEnemy:
                    // TODO: Spawn enemy at player location
                    Debug.Log($"[StoryScriptEngine] Spawn enemy: {evt.parameter}");
                    break;

                case StoryEventType.CompleteChapter:
                    CompleteChapter(evt.parameter);
                    break;

                case StoryEventType.EnablePlayer:
                    var player = GameObject.FindGameObjectWithTag("Player");
                    if (player != null)
                    {
                        var pc = player.GetComponent<PlayerController>();
                        if (pc != null) pc.enabled = true;
                    }
                    break;

                case StoryEventType.DisablePlayer:
                    var player2 = GameObject.FindGameObjectWithTag("Player");
                    if (player2 != null)
                    {
                        var pc2 = player2.GetComponent<PlayerController>();
                        if (pc2 != null) pc2.enabled = false;
                    }
                    break;

                case StoryEventType.GrantItem:
                    var inv = InventoryManager.Instance;
                    if (inv != null) inv.AddItem(evt.parameter, 1);
                    break;

                case StoryEventType.PlayAudio:
                    // TODO: Play audio
                    Debug.Log($"[StoryScriptEngine] Play audio: {evt.parameter}");
                    break;

                case StoryEventType.TeleportPlayer:
                    var p = GameObject.FindGameObjectWithTag("Player");
                    if (p != null)
                    {
                        var target = GameObject.Find(evt.parameter);
                        if (target != null)
                        {
                            p.transform.position = target.transform.position;
                        }
                    }
                    break;

                default:
                    Debug.LogWarning($"[StoryScriptEngine] Unknown event type: {evt.eventType}");
                    break;
            }
        }

        public void SetStoryFlag(string flag, bool value = true)
        {
            storyFlags[flag] = value;
            OnStoryFlagSet?.Invoke(flag);
            Debug.Log($"[StoryScriptEngine] Flag set: {flag} = {value}");
        }

        public bool GetStoryFlag(string flag)
        {
            return storyFlags.TryGetValue(flag, out bool value) && value;
        }

        /// <summary>
        /// Checks if a sequence trigger condition is met and fires the sequence.
        /// Called by external systems (region transitions, quest completions, etc.)
        /// </summary>
        public void CheckTrigger(SequenceTriggerType triggerType, string triggerData)
        {
            if (activeChapter == null) return;

            foreach (var sequence in activeChapter.sequences)
            {
                if (sequence.triggerType == triggerType && sequence.triggerData == triggerData)
                {
                    TriggerSequence(sequence.sequenceId);
                }
            }
        }

        public StoryChapter GetActiveChapter() => activeChapter;
        public bool IsSequenceActive => isSequenceActive;
    }

    // === Data Structures ===

    [Serializable]
    public class StoryChapter
    {
        public string chapterId;
        public int chapterNumber;
        public string name;
        [TextArea(2, 4)]
        public string description;
        public string regionId;
        public List<StorySequence> sequences = new List<StorySequence>();
    }

    [Serializable]
    public class StorySequence
    {
        public string sequenceId;
        public string name;
        [TextArea(2, 4)]
        public string description;
        public SequenceTriggerType triggerType;
        public string triggerData;
        public List<StoryEvent> events = new List<StoryEvent>();
    }

    public enum SequenceTriggerType
    {
        OnRegionEnter,
        OnRegionTransition,
        OnQuestCompleted,
        OnQuestAccepted,
        OnWaypointReached,
        OnStoryFlagSet,
        OnEnemyDefeated,
        OnItemCollected,
        Manual
    }

    [Serializable]
    public class StoryEvent
    {
        public StoryEventType eventType;
        public string parameter;
        public float delay;

        public StoryEvent() { }

        public StoryEvent(StoryEventType type, string param, float d = 0f)
        {
            eventType = type;
            parameter = param;
            delay = d;
        }
    }

    public enum StoryEventType
    {
        PlayCutscene,
        AcceptQuest,
        CompleteQuest,
        UpdateQuest,
        DisplayNarration,
        SetStoryFlag,
        SpawnEnemy,
        CompleteChapter,
        EnablePlayer,
        DisablePlayer,
        GrantItem,
        PlayAudio,
        TeleportPlayer
    }
}
