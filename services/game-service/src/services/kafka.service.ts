/**
 * Kafka producer — game event publisher.
 *
 * Publishes game.session.completed events consumed by the
 * analytics_aggregator Airflow DAG → DuckDB pipeline.
 *
 * Wire-up: call kafkaService.publishSessionCompleted() at the end of
 * session.service.ts completeSession() after updating the DB.
 *
 * Dependency: add "kafkajs": "^2.2.4" to services/game-service/package.json
 */

import { Kafka, Producer, Partitioners } from 'kafkajs';

const TOPIC_SESSION_COMPLETED = 'game.session.completed';

interface SessionCompletedEvent {
    event_type: 'session.completed';
    user_id: string;
    puzzle_id: string;
    session_id: string;
    difficulty: string;
    time_elapsed_ms: number;
    score: number;
    hints_used: number;
    errors_count: number;
    completed_at: string; // ISO 8601
}

class KafkaService {
    private kafka: Kafka | null = null;
    private producer: Producer | null = null;
    private connected = false;

    private get brokers(): string[] {
        return (process.env.KAFKA_BROKERS ?? 'kafka:9092').split(',');
    }

    async connect(): Promise<void> {
        if (this.connected) return;
        try {
            this.kafka = new Kafka({
                clientId: 'game-service',
                brokers: this.brokers,
                retry: { retries: 3 },
            });
            this.producer = this.kafka.producer({
                createPartitioner: Partitioners.LegacyPartitioner,
            });
            await this.producer.connect();
            this.connected = true;
        } catch (err) {
            // Non-fatal — analytics is best-effort; gameplay must not be blocked.
            console.warn('[KafkaService] Could not connect, analytics publishing disabled:', err);
        }
    }

    async disconnect(): Promise<void> {
        if (this.producer && this.connected) {
            await this.producer.disconnect().catch(() => {});
        }
        this.connected = false;
    }

    /**
     * Publish a session.completed event. Fire-and-forget — never throws,
     * so a Kafka outage cannot break the gameplay path.
     */
    async publishSessionCompleted(payload: Omit<SessionCompletedEvent, 'event_type'>): Promise<void> {
        if (!this.producer || !this.connected) return;

        const event: SessionCompletedEvent = {
            event_type: 'session.completed',
            ...payload,
        };

        try {
            await this.producer.send({
                topic: TOPIC_SESSION_COMPLETED,
                messages: [
                    {
                        key: payload.user_id,
                        value: JSON.stringify(event),
                    },
                ],
            });
        } catch (err) {
            // Log but do not rethrow — analytics is non-critical.
            console.warn('[KafkaService] Failed to publish session event:', err);
        }
    }
}

export const kafkaService = new KafkaService();
