using UnityEngine;
using System.Collections.Generic;

namespace UnreliableProphecy
{
    /// <summary>
    /// Audio system for dialogue interactions. Plays UI sounds, ambient cues,
    /// and typewriter click effects. Supports multiple audio sources for
    /// overlapping sounds.
    /// 
    /// Audio cues:
    /// - Dialogue open (parchment unfurl)
    /// - Dialogue advance (page turn)
    /// - Typewriter click (per character)
    /// - Dialogue close (parchment roll)
    /// - AI generation start (quill scratch)
    /// - AI generation complete (ink dip)
    /// - NPC greeting (unique per NPC type)
    /// </summary>
    public class DialogueAudio : MonoBehaviour
    {
        public static DialogueAudio Instance { get; private set; }

        [Header("Audio Sources")]
        public AudioSource uiSource;
        public AudioSource typewriterSource;
        public AudioSource ambientSource;

        [Header("UI Sounds")]
        public AudioClip dialogueOpen;
        public AudioClip dialogueAdvance;
        public AudioClip dialogueClose;
        public AudioClip typewriterClick;
        public AudioClip aiGenerationStart;
        public AudioClip aiGenerationComplete;
        public AudioClip npcGreeting;
        public AudioClip npcFarewell;

        [Header("Settings")]
        [Range(0f, 1f)]
        public float uiVolume = 0.7f;
        [Range(0f, 1f)]
        public float typewriterVolume = 0.3f;
        [Range(0f, 1f)]
        public float ambientVolume = 0.5f;
        public float typewriterClickInterval = 0.05f;

        // State
        private Dictionary<string, AudioClip> npcGreetingClips = new Dictionary<string, AudioClip>();
        private float lastClickTime;
        private bool isTypewriterActive = false;

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);

            // Create sources if not assigned
            if (uiSource == null)
            {
                uiSource = gameObject.AddComponent<AudioSource>();
                uiSource.playOnAwake = false;
            }
            if (typewriterSource == null)
            {
                typewriterSource = gameObject.AddComponent<AudioSource>();
                typewriterSource.playOnAwake = false;
            }
            if (ambientSource == null)
            {
                ambientSource = gameObject.AddComponent<AudioSource>();
                ambientSource.playOnAwake = false;
            }

            uiSource.volume = uiVolume;
            typewriterSource.volume = typewriterVolume;
            ambientSource.volume = ambientVolume;
        }

        /// <summary>
        /// Plays the dialogue open sound.
        /// </summary>
        public void PlayDialogueOpen()
        {
            if (dialogueOpen != null)
                uiSource.PlayOneShot(dialogueOpen, uiVolume);
        }

        /// <summary>
        /// Plays the dialogue advance sound.
        /// </summary>
        public void PlayDialogueAdvance()
        {
            if (dialogueAdvance != null)
                uiSource.PlayOneShot(dialogueAdvance, uiVolume);
        }

        /// <summary>
        /// Plays the dialogue close sound.
        /// </summary>
        public void PlayDialogueClose()
        {
            if (dialogueClose != null)
                uiSource.PlayOneShot(dialogueClose, uiVolume);
        }

        /// <summary>
        /// Plays a typewriter click sound (rate-limited).
        /// </summary>
        public void PlayTypewriterClick()
        {
            if (typewriterClick == null) return;
            if (Time.time - lastClickTime < typewriterClickInterval) return;
            lastClickTime = Time.time;
            typewriterSource.PlayOneShot(typewriterClick, typewriterVolume);
        }

        /// <summary>
        /// Plays the AI generation start sound.
        /// </summary>
        public void PlayAIGenerationStart()
        {
            if (aiGenerationStart != null)
                uiSource.PlayOneShot(aiGenerationStart, uiVolume);
        }

        /// <summary>
        /// Plays the AI generation complete sound.
        /// </summary>
        public void PlayAIGenerationComplete()
        {
            if (aiGenerationComplete != null)
                uiSource.PlayOneShot(aiGenerationComplete, uiVolume);
        }

        /// <summary>
        /// Plays an NPC greeting sound.
        /// </summary>
        public void PlayNpcGreeting()
        {
            if (npcGreeting != null)
                uiSource.PlayOneShot(npcGreeting, uiVolume);
        }

        /// <summary>
        /// Plays an NPC farewell sound.
        /// </summary>
        public void PlayNpcFarewell()
        {
            if (npcFarewell != null)
                uiSource.PlayOneShot(npcFarewell, uiVolume);
        }

        /// <summary>
        /// Sets the typewriter active state (controls click playback).
        /// </summary>
        public void SetTypewriterActive(bool active)
        {
            isTypewriterActive = active;
        }

        /// <summary>
        /// Registers a custom greeting sound for an NPC type.
        /// </summary>
        public void RegisterNpcGreeting(string npcId, AudioClip clip)
        {
            npcGreetingClips[npcId] = clip;
        }

        /// <summary>
        /// Plays a custom greeting for the NPC if registered.
        /// </summary>
        public void PlayCustomNpcGreeting(string npcId)
        {
            if (npcGreetingClips.TryGetValue(npcId, out var clip) && clip != null)
            {
                uiSource.PlayOneShot(clip, uiVolume);
            }
            else
            {
                PlayNpcGreeting();
            }
        }

        /// <summary>
        /// Stops all dialogue audio.
        /// </summary>
        public void StopAll()
        {
            uiSource.Stop();
            typewriterSource.Stop();
            ambientSource.Stop();
        }

        /// <summary>
        /// Sets the master volume for all dialogue audio.
        /// </summary>
        public void SetMasterVolume(float volume)
        {
            uiVolume = Mathf.Clamp01(volume);
            typewriterVolume = uiVolume * 0.4f;
            ambientVolume = uiVolume * 0.7f;
            uiSource.volume = uiVolume;
            typewriterSource.volume = typewriterVolume;
            ambientSource.volume = ambientVolume;
        }
    }
}