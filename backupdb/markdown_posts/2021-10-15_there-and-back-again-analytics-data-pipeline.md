# There and back again - Analytics Data Pipeline

As an architect it's my job to talk and write a lot of bollocks. One must constantly be on the forefront of buzzword lore to maintain ones architectural standing and feeling of general superiority over lesser IT peons.

However, in this obviously correct and proper feudal type system, what sometimes gets lost or confused is the practicality of implementation and shared understanding. The same architectural buzzwords can be interpreted in so many ways so it becomes difficult for people implementing to realise the actual benefit. This means uninspired doers either take no notice or go off on a tangent which looses any architectural benefit intended.

This is why I'm not a fan of ivory tower architects and IT leaders who shoot Google arrows and Gartner bolts from the parapet (at least in the data domain), and I prefer to wield a bloody big sword in the melee of IT implementation. This blog is about a quick PoC I had a bash at for a pipeline which streams from a simulated on-prem source to a data lake-house.

---

The architectural concept that I'm promoting at the moment is data convergence and specifically shared streaming pipelines for operational and analytical use cases. My main opponent in this battle is my arch-nemesis - Conway's Law. Every implementation squad knows how to get their backlog done and knows that being dependent on other teams will only slow them down so convergence is looked upon with suspicion and inflated estimates. I know it's shooting the messenger, but damn you Conway!

Native cloud tech has given Conway (yes, I'm anthropomorphising now) a huge weapon with which to cut silos into IT. It's very easy and quick to get things done in the cloud which means squads can do more "quick wins" and "thin slices" with less involvement from other teams, egged on by consultants and often without realizing how the lost strategic opportunity can harm the data landscape and slow down overall IT transformation.

---

### Overview

Enough with the wistful ranting Semprini, you beguiling IT philanderer I hear you exclaim. Indeed! onto some implementation.

My constraints going in to this PoC was a logical architecture in-line with the strategic direction for my organisation. The proof I'm looking for is that the speed of transforming via real-time operational techniques like microservices and transporting via streams is no more overhead than batch ETL/ELT. Here's the overview:

![data pipeline test.png](https://s3.ap-southeast-2.amazonaws.com/semprini.me/media/images/data_pipeline_test.width-800.png)

The architectural intent is to replace batch system to system integration with an event driven architecture and while doing so create a suite of data products which will form a data mesh. Doing this right means we can deprecate giant swathes of legacy IT platforms. Doing it wrong introduces coupling and dependency on these legacy platforms.

Step 1: Application Abstraction / Data On-ramp

Step 2: Canonical Data Products

Step 3: Analytics Query

Step 4: Gloat over Conway's defeated corpse

---

### Step 1: Application Abstraction / Data On-ramp

Many legacy monoliths don't admit that other systems exist and will begrudgingly allow Change Data Capture to export tables with odd schema which only makes sense to that system. No one else should have to care about this so the role of the abstraction layer is to handle these shenanigans, publishing and subscribing from canonical Kafka topics. I created a simple synthetic data generator in python which mimics a CDC output of raw tables in JSON format:

[GitHub: producer.py](https://github.com/Semprini/semprini-blog-pipeline/blob/main/producer.py)

We then needed a way to get it out of on-prem into AWS so I created a forwarder which invokes an AWS Lambda:

[GitHub: replicator.py](https://github.com/Semprini/semprini-blog-pipeline/blob/main/replicator.py)

The lambda first archives the raw data by sending it to AWS Firehose so it can buffer into AWS S3. Next it transforms the input to the canonical form and delivers to AWS MSK. I wanted to show how the source systems view of customer may not match the business view of customer so the source has personal information about the customer in the raw table which is split into customer and individual. The logs go to CloudWatch to be used for data lineage.

[GitHub: AWS Lambda py](https://github.com/Semprini/semprini-blog-pipeline/blob/main/test_kafka_s3/lambda_function.py)

This completes the abstraction layer of my source system. Once we do this in reverse where the application abstraction is subscribing to the data it needs, we have an event driven architecture up and running which has loosely coupled legacy application from business data.

---

### Step 2 - Canonical Data Products

To decouple from legacy systems we need to materialise significant business data away from how our applications see the world. The features of these data products are interfaces, storage and master data management for operational and analytic data. This is simply a convergence of what we already do in the layers of data lakehouses and operational integration.

For this PoC I'm not worrying about the operational storage or API interfaces, that can be plugged in later to the canonical topics.

The streaming interface is a simple MSK topic per data object so customer, individual and account. It feels weird that the MSK interface doesn't allow topic creation so I fired up a little EC2 instance to create topics:

`sudo yum install java-1.8.0`

`wget https://archive.apache.org/dist/kafka/2.2.1/kafka_2.12-2.2.1.tgz`

`tar -xzf kafka_2.12-2.2.1.tgz`

`cd kafka_2.12-2.2.1/`

`aws configure`

`bin/kafka-topics.sh --create --zookeeper "<msk cluster>" --replication-factor 2 --partitions 1 --topic customer`

`bin/kafka-topics.sh --create --zookeeper "<msk cluster>" --replication-factor 2 --partitions 1 --topic individual`

`bin/kafka-topics.sh --create --zookeeper "<msk cluster>" --replication-factor 2 --partitions 1 --topic account`

Consuming from these topics are spark streaming jobs which will save via Delta Lake (parquet with twiddly bits) format into S3. The Delta Lake library will do the buffering for us as it uses the [AWS Hadoop module](https://hadoop.apache.org/docs/stable/hadoop-aws/tools/hadoop-aws/index.html) so no need of Firehose here.

![data pipeline glue studio2.png](https://s3.ap-southeast-2.amazonaws.com/semprini.me/media/images/data_pipeline_glue_studio2.width-800.png)

For the later operational interface, the spark job will also store in PostgreSQL which will be fronted by an API interface.

---

### Step 3 - Analytics Query

Simply start using Athena. The customer, individual and account have been recorded in the glue catalog and is ready to go.

The next step, beyond the scope of this PoC is to implement [Automated Operational to Analytics Transform](./2021-04-05_automated-operational-analytics-transform.md) which programmatically generates delta lake views by joining the tables using the canonical data model.
