# Enterprise Microservices

![architecture.JPG](https://s3.ap-southeast-2.amazonaws.com/semprini.me/media/images/architecture.2e16d0ba.fill-800x240.jpg)

If you have a "microservice" which exposes an API calling a back end system, you don't have a microservice - you have an API. Your API has wisely used some of the concepts of microservice architecture. Microservice architecture is not an integration architecture, it's an application architecture and applications are responsible for business logic. This distinction is important because the beauty of microservice architecture is both technical and behavioural.

However, I'll extend an olive branch to the API people, no doubt aghast by my blasphemy, by calling them "integration microservices".

Integration microservices are fine I guess, but too often they are used, just as integration is often used, to sweep the legacy monster under the carpet so we don't have to see it - out of sight, out of mind. We implement integration microservices containerised, auto-scaling, auto-healing etc, IT management has an orgasm, we all add something to our CVs and the legacy monster waits.

---

I'd like to make the distinction from integration microservices trendy by using the term "Enterprise" micro-services which are distinct in two ways:

1. The scope of an enterprise micro-service is defined by the business model (I suggest an industry standard model E.g. BIAN (banking) or TAM (telco)) not technology factors. In a corporate entity we should stop thinking of applications and organise IT around the way the business is structured.
2. Data identified as "Significant Business Objects" should not be mastered in the micro-service but in domain aligned data products forming a data mesh. You can find the rationale for this in my [Data Autonomy](./2019-02-17_data-autonomy-overview.md) posts. This is seen by some to violate the distributed data management principle but it actually separates business logic from data and the mesh products are distributed in-line with data governance.

Enterprise micro-services are a compatible Solution Architecture for a Component Architecture Model as they follow the same principle of decomposition to atomic building blocks. To match the operation model, enterprise micro-services are organized around business capability and are consumed as suites of independently deployable services.

The capability or service model defines the scope of each microservice, the microservice is built to work natively with the domain data model and there are small changes made regularly as the data model changes.

---

#### Limiting Dependencies

A common issue with a micro-service architecture is how to make them atomic. At the start of the move to micro-services, some low hanging processes can be found but after a while each new micro-service has dependencies on data or logic in other services. A great little sketch on this can be seen here:

The standard way to approach this coupling is by using traditional integration architectures & service mesh to (theoretically) decouple the services and expose a suite of clean services. This approach improves things from an integration point of view as we have huge benefits to CI/CD, infrastructure, scaling etc but not to the overall enterprise landscape.

It is not possible to eliminate dependency but since data models mature over time compared to a service model which should constantly be changing with the business we can master data outside our micro-services as business domain specific models. This means the micro-services become dependent on the businesses own semantics. This separation of business logic from business data is the key to limiting dependency. Holistic data models evolve differently than business process as discussed here: [Data Autonomy Overview](./2019-02-17_data-autonomy-overview.md)

---

#### DevOps Support Model

One complexity of a micro-service architecture is how to support the plethora of code bases & technology.

You almost don't have to for a few of reasons:

1. Level 3 support is the ambulance at the bottom of the cliff. With a DevOps ethos we fail fast and early. The smaller atomic building blocks of micro-services allow simpler self-healing and more obvious documentation and testing. I.e. fewer problems to support
2. If you have ever worked on a large monolith code base then you'll know that you are often faced with a defect in a section of code which you know nothing about and with many things using the buggy section of code . With enterprise microservices the code is built to do a single business purpose making it much easier to come at cold - especially since the data is all governed in the data mesh.
3. Quite often when I have debugged code in a monolith I ask myself what the original coder (possibly me) was smoking, throw it away and do it properly. Once again, micro-services make this much easier. If you don't like what the micro-service is doing - throw it away and do it some other way. There's little investment in each micro-service.

You could just use an IT consultancy for this support, especially if you freely share the domain business model with your partners.

---

#### Microservice patterns & boilerplate

A common microservice pattern in a event driven architecture is the ‘Queue Trigger Pattern’. In this pattern a microservice is triggered by an event message, it runs a piece of business logic and generates changed "significant business objects" which can be published back to the data platform.

The pattern doesn’t impose a technology, but it does enable exemplars to be created which provide the boilerplate of a micro-service. If you have a service mesh then some of this will be done for you in the sidecar.

The queue trigger pattern exemplar will provide:

- Subscription to queues/topic
- Recoverable and non-recoverable exception handling
- Retry queues
- Dead-letter queues
- Logging

Since RESTful events subscribed to have HATEOAS links, the microservice can easily link to APIs which provide any extra significant data required. The micro-service can then publish new/changed data entities or POST/PUT the data via APIs.

A python exemplar can be found here: [Github: CBE / Queue Trigger Pattern](https://github.com/Semprini/cbe/blob/master/cbe/cbe/utils/microservices/queue_trigger_pattern.py)
