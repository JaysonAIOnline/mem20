using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.Controls;

namespace UnreliableProphecy
{
    /// <summary>
    /// Third-person player controller for The Unreliable Prophecy.
    /// Supports keyboard/mouse and gamepad. Movement, sprint, interaction.
    /// </summary>
    public class PlayerController : MonoBehaviour
    {
        [Header("Movement")]
        public float walkSpeed = 3f;
        public float sprintSpeed = 6f;
        public float rotationSpeed = 10f;
        public float gravity = -9.81f;
        public float jumpHeight = 1.5f;

        [Header("References")]
        public CharacterController controller;
        public Transform cameraTransform;

        [Header("Combat")]
        public float ability1Cooldown = 6f;
        public float ability2Cooldown = 4f;

        // State
        Vector3 velocity;
        bool isGrounded;
        float ability1Timer;
        float ability2Timer;
        float currentSpeed;

        // Input
        Vector2 moveInput;
        bool sprintHeld;
        bool jumpPressed;
        bool interactPressed;
        bool ability1Pressed;
        bool ability2Pressed;

        // Public getters for SaveSystem
        public float GetAbility1Cooldown() => ability1Timer;
        public float GetAbility2Cooldown() => ability2Timer;

        // Components
        Animator animator;

        void Awake()
        {
            if (controller == null) controller = GetComponent<CharacterController>();
            if (cameraTransform == null) cameraTransform = Camera.main.transform;
            animator = GetComponent<Animator>();

            // Lock cursor
            Cursor.lockState = CursorLockMode.Locked;
            Cursor.visible = false;
        }

        void Update()
        {
            HandleInput();
            HandleMovement();
            HandleCooldowns();

            // Update animator
            if (animator != null)
            {
                animator.SetFloat("Speed", controller.velocity.magnitude);
                animator.SetBool("Grounded", isGrounded);
            }
        }

        void HandleInput()
        {
            var keyboard = Keyboard.current;
            var gamepad = Gamepad.current;

            // Movement
            Vector2 input = Vector2.zero;
            if (keyboard != null)
            {
                if (keyboard.wKey.isPressed) input.y += 1;
                if (keyboard.sKey.isPressed) input.y -= 1;
                if (keyboard.dKey.isPressed) input.x += 1;
                if (keyboard.aKey.isPressed) input.x -= 1;
            }
            if (gamepad != null)
            {
                input += gamepad.leftStick.ReadValue();
            }
            moveInput = Vector2.ClampMagnitude(input, 1f);

            // Sprint
            sprintHeld = keyboard?.leftShiftKey.isPressed == true || gamepad?.leftStickButton.isPressed == true;

            // Jump
            jumpPressed = keyboard?.spaceKey.wasPressedThisFrame == true || gamepad?.buttonSouth.wasPressedThisFrame == true;

            // Interact
            interactPressed = keyboard?.eKey.wasPressedThisFrame == true || gamepad?.buttonWest.wasPressedThisFrame == true;

            // Abilities
            ability1Pressed = keyboard?.qKey.wasPressedThisFrame == true || gamepad?.rightTrigger.wasPressedThisFrame == true;
            ability2Pressed = keyboard?.rKey.wasPressedThisFrame == true || gamepad?.leftTrigger.wasPressedThisFrame == true;
        }

        void HandleMovement()
        {
            isGrounded = controller.isGrounded;
            if (isGrounded && velocity.y < 0) velocity.y = -2f;

            // Calculate move direction relative to camera
            Vector3 forward = cameraTransform.forward;
            Vector3 right = cameraTransform.right;
            forward.y = 0;
            right.y = 0;
            forward.Normalize();
            right.Normalize();

            Vector3 moveDir = (forward * moveInput.y + right * moveInput.x).normalized;

            currentSpeed = sprintHeld ? sprintSpeed : walkSpeed;
            controller.Move(moveDir * currentSpeed * Time.deltaTime);

            // Rotation
            if (moveDir != Vector3.zero)
            {
                Quaternion targetRotation = Quaternion.LookRotation(moveDir);
                transform.rotation = Quaternion.Slerp(transform.rotation, targetRotation, rotationSpeed * Time.deltaTime);
            }

            // Jump
            if (jumpPressed && isGrounded)
            {
                velocity.y = Mathf.Sqrt(jumpHeight * -2f * gravity);
            }

            // Gravity
            velocity.y += gravity * Time.deltaTime;
            controller.Move(velocity * Time.deltaTime);

            // Interact
            if (interactPressed)
            {
                Interact();
            }

            // Abilities
            if (ability1Pressed && ability1Timer <= 0)
            {
                ActivateAbility1();
                ability1Timer = ability1Cooldown;
            }
            if (ability2Pressed && ability2Timer <= 0)
            {
                ActivateAbility2();
                ability2Timer = ability2Cooldown;
            }
        }

        void HandleCooldowns()
        {
            if (ability1Timer > 0) ability1Timer -= Time.deltaTime;
            if (ability2Timer > 0) ability2Timer -= Time.deltaTime;
        }

        void Interact()
        {
            Ray ray = new Ray(cameraTransform.position, cameraTransform.forward);
            if (Physics.Raycast(ray, out RaycastHit hit, 3f))
            {
                var interactable = hit.collider.GetComponent<IInteractable>();
                interactable?.Interact(this);
            }
        }

        void ActivateAbility1()
        {
            // Primary ability - dash/attack
            Debug.Log("Ability 1 activated");
            // TODO: Implement dash or attack
        }

        void ActivateAbility2()
        {
            // Secondary ability - scan/shield
            Debug.Log("Ability 2 activated");
            // TODO: Implement scan or shield
        }

        public void AddVelocity(Vector3 vel)
        {
            velocity += vel;
        }
    }
}