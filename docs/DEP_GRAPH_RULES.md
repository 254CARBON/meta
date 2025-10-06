# Dependency Graph Rules

> Architecture principles and validation rules for the 254Carbon platform dependency graph

**Version:** 1.0.0  
**Last Updated:** 2025-10-06

---

## Table of Contents
1. Architecture Principles
2. Domain Layering
3. Dependency Directionality
4. Forbidden Patterns
5. External Dependencies
6. Validation Algorithm
7. Remediation Strategies

---

## 1. Architecture Principles

The 254Carbon platform follows a **layered architecture** with strict dependency rules to ensure:

- **Maintainability:** Clear separation of concerns
- **Scalability:** Independent service deployment
- **Testability:** Isolated testing without full platform
- **Reliability:** Changes don't cascade unexpectedly

### Core Principles

1. **Acyclic Dependencies:** No circular dependencies allowed
2. **Directional Cohesion:** Lower layers don't depend on higher layers
3. **Explicit Contracts:** Dependencies declared in manifests
4. **External Whitelist:** Only approved external systems

---

## 2. Domain Layering

Services are organized into 5 architectural layers:

```
Layer 5: ML (Analytics & Prediction)
         ↑
Layer 4: Data Processing (Ingestion & Transformation)
         ↑  
Layer 3: Access (API Gateway & Auth)
         ↑
Layer 2: Shared (Common Utilities)
         ↑
Layer 1: Infrastructure (Core Services)
```

###  Layer Definitions

| Layer | Domain | Purpose | Can Depend On |
|-------|--------|---------|---------------|
| 1 | `infrastructure` | Core platform services | External only |
| 2 | `shared` | Common utilities, libraries | Infrastructure, External |
| 3 | `access` | API gateway, authentication | Shared, Infrastructure, External |
| 4 | `data-processing` | Data ingestion, normalization | Access, Shared, Infrastructure, External |
| 5 | `ml` | ML models, analytics | Data-Processing, Access, Shared, External |

### Layer Rules

✅ **ALLOWED:**
- Higher layers depending on lower layers (e.g., ML → Data-Processing)
- Same-layer dependencies (with care to avoid cycles)
- Any layer depending on external systems

❌ **FORBIDDEN:**
- Lower layers depending on higher layers (e.g., Access → ML)
- Infrastructure depending on application layers
- Shared depending on domain-specific services

---

## 3. Dependency Directionality

### Rule: Dependencies Flow Downward

**Services in higher layers can depend on services in lower layers, but not vice versa.**

#### Valid Dependency Flows

```
✅ ml/curve → data-processing/aggregation (higher → lower)
✅ data-processing/streaming → access/auth (higher → lower)
✅ access/gateway → shared/metrics (higher → lower)
✅ shared/metrics → infrastructure/logging (higher → lower)
```

#### Invalid Dependency Flows

```
❌ access/gateway → data-processing/streaming (lower → higher)
❌ shared/utilities → access/auth (lower → higher)
❌ infrastructure → ml/curve (layer 1 → layer 5)
```

### Enforcement

The `validate_graph.py` script checks directionality by:
1. Mapping each service to its layer number (1-5)
2. For each dependency edge, comparing layer numbers
3. Failing validation if `from_layer < to_layer`

**Configuration:** Layer mappings in `config/rules.yaml`:

```yaml
dependency:
  domain_layers:
    infrastructure: 1
    shared: 2
    access: 3
    data-processing: 4
    ml: 5
```

---

## 4. Forbidden Patterns

### Pattern 1: Access → Data-Processing

**Rule:** Access layer services MUST NOT depend on data-processing services

**Rationale:**
- Access layer is entry point and should be lightweight
- Data-processing is compute-intensive and higher layer
- Violates separation of concerns

**Example Violation:**
```yaml
# ❌ BAD: Gateway depending on streaming
name: gateway
domain: access
dependencies:
  internal:
    - streaming  # streaming is in data-processing domain
```

**Solution:** Use event-driven communication or API contracts

### Pattern 2: Shared → Domain-Specific

**Rule:** Shared utilities MUST NOT depend on domain-specific services

**Rationale:**
- Shared code should be reusable across domains
- Domain dependencies create tight coupling
- Breaks modularity principle

**Example Violation:**
```yaml
# ❌ BAD: Shared metrics depending on gateway
name: metrics
domain: shared
dependencies:
  internal:
    - gateway  # gateway is domain-specific
```

**Solution:** Use dependency injection or plugin architecture

### Pattern 3: Circular Dependencies

**Rule:** NO service cycles allowed (A → B → A)

**Example Violation:**
```yaml
# Service A
dependencies:
  internal: [service-b]

# Service B  
dependencies:
  internal: [service-a]  # ❌ Creates cycle!
```

**Solution:** Extract common functionality to shared layer

---

## 5. External Dependencies

### Approved External Dependencies

Services may depend on these external systems:

**Data Stores:**
- `redis` - Caching and pub/sub
- `clickhouse` - Analytics database
- `postgresql` - Relational database  
- `mongodb` - Document database
- `elasticsearch` - Search and analytics

**Message Queues:**
- `kafka` - Event streaming
- `rabbitmq` - Message broker

**Infrastructure:**
- `nginx` - Reverse proxy
- `envoy` - Service mesh
- `istio` - Service mesh platform
- `cert-manager` - Certificate management

**Observability:**
- `prometheus` - Metrics collection
- `grafana` - Visualization
- `datadog` - APM platform

### Adding New External Dependencies

**Process:**
1. **Justify:** Document why dependency is needed
2. **Evaluate:** Security review, licensing check
3. **Approve:** Architecture team sign-off
4. **Update Whitelist:** Add to `config/rules.yaml`
5. **Document:** Update this file with rationale

**Configuration:**
```yaml
# config/rules.yaml
dependency:
  allowed_external:
    - redis
    - clickhouse
    # ... add new entries here
```

---

## 6. Validation Algorithm

### Cycle Detection (DFS)

The system uses **Depth-First Search** to detect cycles:

```python
def has_cycle(graph):
    visited = set()
    rec_stack = set()  # Recursion stack
    
    for node in graph.nodes:
        if node not in visited:
            if dfs_cycle_check(node, visited, rec_stack):
                return True, get_cycle_path(rec_stack)
    
    return False, []
```

**Time Complexity:** O(V + E) where V = services, E = dependencies  
**Space Complexity:** O(V) for visited/stack tracking

### Directional Validation

```python
def validate_directionality(service, dependency):
    service_layer = get_layer(service.domain)
    dep_layer = get_layer(dependency.domain)
    
    # Violation if service in lower layer depends on higher layer
    if service_layer < dep_layer:
        return False, f"Reverse dependency: {service.domain} -> {dependency.domain}"
    
    return True, None
```

### External Dependency Check

```python
def validate_external(dependency_name, whitelist):
    if dependency_name not in whitelist:
        return False, f"Unauthorized external dependency: {dependency_name}"
    
    return True, None
```

### Validation Flow

```
1. Load catalog → Extract services
2. Build graph → Create nodes and edges
3. Check cycles → Run DFS algorithm
4. Check directionality → Verify layer rules
5. Check patterns → Apply forbidden pattern rules
6. Check external → Validate against whitelist
7. Generate report → Save violations.json
```

---

## 7. Remediation Strategies

### Remediation 1: Breaking Cycles

**When:** Circular dependency detected

**Strategies:**

**A. Extract Common Functionality**
```
Before: A ⟷ B (cycle)
After:  A → C ← B (common dependency)
```

**B. Event-Driven Communication**
```
Before: A → B → A (cycle via calls)
After:  A → Event Bus ← B (async)
```

**C. Dependency Inversion**
```
Before: A → B → A
After:  A → Interface ← B (dependency injection)
```

### Remediation 2: Fixing Directional Violations

**When:** Lower layer depends on higher layer

**Strategies:**

**A. Move Service to Correct Layer**
- Re-classify service in appropriate domain
- Update manifest `domain` field
- Rebuild catalog

**B. Introduce Abstraction**
- Create interface in lower layer
- Implement interface in higher layer
- Use dependency injection

**C. Use Event-Driven Pattern**
- Higher layer publishes events
- Lower layer subscribes to events
- Decouples direct dependency

### Remediation 3: Unauthorized External Dependencies

**When:** Service uses non-whitelisted external system

**Strategies:**

**A. Request Whitelisting**
- Document use case and justification
- Submit architecture review
- Add to whitelist if approved

**B. Find Alternative**
- Use existing whitelisted alternative
- Refactor to eliminate dependency
- Use internal service instead

**C. Proxy Pattern**
- Create approved proxy service
- Proxy handles external communication
- Services depend on proxy, not external system

### Remediation 4: God Service Refactoring

**When:** Service has excessive dependencies (>6)

**Strategies:**

**A. Domain-Driven Split**
- Identify bounded contexts
- Split by business capability
- Create focused microservices

**B. Facade Pattern**
- Introduce facade service
- Facade aggregates dependencies
- Other services depend on facade only

**C. Event Choreography**
- Replace sync dependencies with events
- Services coordinate via event bus
- Reduces coupling

---

## Appendix C: Example Scenarios

### Scenario 1: New ML Service

**Question:** Can `ml/forecasting` depend on `access/gateway`?

**Analysis:**
- ML is layer 5, Access is layer 3
- Layer 5 can depend on layer 3 ✅
- Dependency is allowed by directionality

**Recommendation:** ✅ Allowed, but consider if this is the right architecture. ML services typically shouldn't call APIs directly—use data lakes instead.

### Scenario 2: Shared Utility

**Question:** Can `shared/logger` depend on `ml/analytics`?

**Analysis:**
- Shared is layer 2, ML is layer 5
- Layer 2 cannot depend on layer 5 ❌
- Violates directional cohesion

**Recommendation:** ❌ Forbidden. Logger should be domain-agnostic. If you need ML-specific logging, create wrapper in ML layer.

### Scenario 3: Adding Cassandra

**Question:** Can we add Cassandra as external dependency?

**Analysis:**
- Cassandra not in whitelist
- Needs architecture approval
- Consider: Do we need another database?

**Process:**
1. Document use case (why not PostgreSQL/ClickHouse?)
2. Architecture review
3. Security review
4. If approved, add to whitelist
5. Update documentation

---

*📚 Part of the 254Carbon Meta documentation suite*  
*See also: [CATALOG_MODEL.md](CATALOG_MODEL.md), [QUALITY_SCORING.md](QUALITY_SCORING.md)*
