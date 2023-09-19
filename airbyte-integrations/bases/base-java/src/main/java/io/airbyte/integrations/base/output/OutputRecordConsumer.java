/*
 * Copyright (c) 2023 Airbyte, Inc., all rights reserved.
 */

package io.airbyte.integrations.base.output;

import io.airbyte.protocol.models.v0.AirbyteMessage;
import java.util.function.Consumer;
import javax.annotation.concurrent.NotThreadSafe;

/**
 * Represents a {@link Consumer} that is used to publish {@link AirbyteMessage} objects for
 * consumption by the platform/destination.
 */
@NotThreadSafe
public interface OutputRecordConsumer extends AutoCloseable, Consumer<AirbyteMessage> {}