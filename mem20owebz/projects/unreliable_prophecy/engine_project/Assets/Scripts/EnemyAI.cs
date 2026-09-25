using UnityEngine;
using UnityEngine.AI;
using System.Collections.Generic;

namespace UnreliableProphecy
{
    /// <summary>
    /// Enemy AI for Bureaucracy Hills enemies.
    /// Patrol, chase, attack, die with bureaucratic flair.
    /// </summary>
    [RequireComponent(typeof(NavMeshAgent))]
    [RequireComponent(typeof(Health))]
    public class EnemyAI : MonoBehaviour
    {
        public enum EnemyType { MisfiledSkeleton, InkBlot, Generic }
        
        [Header("AI Settings")]
        public float patrolRadius = 10f;
        public float detectRadius = 15f;
        public float attackRadius = 2f;
        public float moveSpeed = 3f;
        public float chaseSpeed = 5f;
        public float attackCooldown = 2f;
        public int damage = 10;
        public EnemyType type = EnemyType.Generic;
        public string enemyId;
        
        [Header("Patrol Points")]
        public Transform[] patrolPoints;
        
        [Header("Loot")]
        public List<string> lootTable = new List<string>();
        public float lootChance = 0.3f;
        
        NavMeshAgent agent;
        Health health;
        Transform player;
        Vector3 homePosition;
        int currentPatrolIndex = 0;
        float attackTimer = 0f;
        bool isChasing = false;
        
        enum State { Patrol, Chase, Attack, Dead }
        State currentState = State.Patrol;
        
        void Awake()
        {
            agent = GetComponent<NavMeshAgent>();
            health = GetComponent<Health>();
            homePosition = transform.position;
            
            agent.speed = moveSpeed;
            agent.stoppingDistance = attackRadius * 0.9f;
        }
        
        void Start()
        {
            player = GameObject.FindGameObjectWithTag("Player")?.transform;
            if (patrolPoints.Length == 0)
            {
                // Auto-generate patrol points around home
                GeneratePatrolPoints();
            }
        }
        
        void GeneratePatrolPoints()
        {
            patrolPoints = new Transform[4];
            for (int i = 0; i < 4; i++)
            {
                Vector3 offset = Random.insideUnitSphere * patrolRadius;
                offset.y = 0;
                var pt = new GameObject($"PatrolPoint_{i}").transform;
                pt.position = homePosition + offset;
                pt.parent = transform;
                patrolPoints[i] = pt;
            }
        }
        
        void Update()
        {
            if (health.currentHealth <= 0)
            {
                if (currentState != State.Dead)
                    Die();
                return;
            }
            
            attackTimer -= Time.deltaTime;
            
            float distToPlayer = player ? Vector3.Distance(transform.position, player.position) : float.MaxValue;
            
            switch (currentState)
            {
                case State.Patrol:
                    Patrol();
                    if (distToPlayer <= detectRadius)
                        currentState = State.Chase;
                    break;
                    
                case State.Chase:
                    Chase();
                    if (distToPlayer <= attackRadius)
                        currentState = State.Attack;
                    else if (distToPlayer > detectRadius * 1.5f)
                        currentState = State.Patrol;
                    break;
                    
                case State.Attack:
                    Attack();
                    if (distToPlayer > attackRadius)
                        currentState = State.Chase;
                    break;
            }
        }
        
        void Patrol()
        {
            agent.speed = moveSpeed;
            
            if (agent.remainingDistance < 0.5f)
            {
                currentPatrolIndex = (currentPatrolIndex + 1) % patrolPoints.Length;
                agent.SetDestination(patrolPoints[currentPatrolIndex].position);
            }
        }
        
        void Chase()
        {
            agent.speed = chaseSpeed;
            agent.SetDestination(player.position);
        }
        
        void Attack()
        {
            agent.isStopped = true;
            transform.LookAt(new Vector3(player.position.x, transform.position.y, player.position.z));
            
            if (attackTimer <= 0)
            {
                // Deal damage to player
                var playerHealth = player.GetComponent<Health>();
                if (playerHealth != null)
                {
                    playerHealth.TakeDamage(damage);
                    Debug.Log($"{name} attacks for {damage} damage!");
                }
                attackTimer = attackCooldown;
            }
        }
        
        void Die()
        {
            currentState = State.Dead;
            agent.enabled = false;
            
            // Drop loot
            if (Random.value < lootChance && lootTable.Count > 0)
            {
                string loot = lootTable[Random.Range(0, lootTable.Count)];
                var lootObj = new GameObject($"Loot_{loot}");
                lootObj.transform.position = transform.position + Vector3.up * 0.5f;
                var interactable = lootObj.AddComponent<FormItem>();
                interactable.formId = loot;
                interactable.formName = loot;
                interactable.interactableName = loot;
                var col = lootObj.AddComponent<SphereCollider>();
                col.isTrigger = true;
                col.radius = 0.5f;
            }
            
            // Play death animation/effect
            Debug.Log($"{name} has been processed.");
            
            // Respawn after delay or destroy
            Destroy(gameObject, 3f);
        }
        
        void OnDrawGizmosSelected()
        {
            Gizmos.color = Color.yellow;
            Gizmos.DrawWireSphere(transform.position, detectRadius);
            Gizmos.color = Color.red;
            Gizmos.DrawWireSphere(transform.position, attackRadius);
        }
    }
}