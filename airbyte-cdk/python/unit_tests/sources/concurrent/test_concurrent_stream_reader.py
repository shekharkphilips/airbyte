#
# Copyright (c) 2023 Airbyte, Inc., all rights reserved.
#
import logging
from queue import Queue
from typing import Any, List, Mapping, Optional, Tuple
from unittest import TestCase
from unittest.mock import Mock

from airbyte_cdk.sources.concurrent.concurrent_abstract_source import ConcurrentAbstractSource, Partition, PartitionGenerator, QueueConsumer
from airbyte_cdk.sources.concurrent.concurrent_stream_reader import ConcurrentStreamReader
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.utils.schema_helpers import InternalConfig


class MockConcurrentAbstractSource(ConcurrentAbstractSource):
    def __init__(self, partition_generator, queue_consumer: QueueConsumer, queue: Queue, streams: List[Stream]):
        super().__init__(partition_generator, queue_consumer, queue, max_workers=1)
        self._streams = streams

    def check_connection(self, logger: logging.Logger, config: Mapping[str, Any]) -> Tuple[bool, Optional[Any]]:
        pass

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        return self._streams


class ConcurrentFullRefreshReadTestCase(TestCase):
    # FIXME: need a test to confirm there are multiple sentinels added to the queue if there's many workers..

    _NO_CURSOR_FIELD = None
    _INTERNAL_CONFIG = InternalConfig()

    def setUp(self):
        self._logger = Mock()
        self._state = None
        self._queue = Queue()
        self._name = "Source"
        self._partition_generator = PartitionGenerator(self._queue, self._name)
        self._queue_consumer = QueueConsumer(self._name)

    def _mock_stream(self, name: str, partitions, records_per_partition, available):
        stream = Mock()
        stream.name = name
        stream.get_json_schema.return_value = {}
        stream.generate_partitions.return_value = iter(partitions)
        stream.read_records.side_effect = [iter(records) for records in records_per_partition]
        if available:
            stream.check_availability.return_value = True, None
        else:
            stream.check_availability.return_value = False, "A reason why the stream is unavailable"
        return stream

    def _mock_configured_catalog(self, streams_to_sync):
        configured_catalog = Mock()
        configured_streams = [Mock() for _ in streams_to_sync]
        for index in range(len(configured_streams)):
            configured_streams[index].stream = streams_to_sync[index]
        configured_catalog.streams = configured_streams
        return configured_catalog

    def _read_messages_with_mocked_emitted_at(self, source, configured_catalog):
        config = {}
        all_messages = list(source.read(self._logger, config, configured_catalog, self._state))
        for message in all_messages:
            message.record.emitted_at = 1
        return all_messages

    def _verify_output_messages(self, actual_messages, expected_messages):
        for expected_message in expected_messages:
            assert expected_message in actual_messages
        assert len(actual_messages) == len(expected_messages)

    def test_read_a_single_stream_with_a_single_partition(self):

        partition = Partition()
        partitions = [partition]

        records = [
            {"id": 1, "partition": 1},
            {"id": 2, "partition": 1},
        ]
        records_per_partition = [records]

        stream = self._mock_stream("A", partitions, records_per_partition, True)
        stream_reader = ConcurrentStreamReader(self._partition_generator, self._queue_consumer, self._queue, 1)

        all_messages = stream_reader.read_stream(stream, self._NO_CURSOR_FIELD, self._INTERNAL_CONFIG, self._logger)

        expected_messages = [
            {"id": 1, "partition": 1},
            {"id": 2, "partition": 1},
        ]

        self._verify_output_messages(all_messages, expected_messages)
        assert self._queue.empty()

    def test_read_a_single_stream_with_two_partitions(self):
        # FIXME what are these partitions?
        partition1 = Partition()
        partition2 = Partition()
        partitions = [partition1, partition2]

        records_partition_1 = [
            {"id": 1, "partition": 1},
            {"id": 2, "partition": 1},
        ]

        records_partition_2 = [
            {"id": 3, "partition": 2},
            {"id": 4, "partition": 2},
        ]
        records_per_partition = [records_partition_1, records_partition_2]
        stream = self._mock_stream("A", partitions, records_per_partition, True)
        stream_reader = ConcurrentStreamReader(self._partition_generator, self._queue_consumer, self._queue, 1)

        all_messages = stream_reader.read_stream(stream, self._NO_CURSOR_FIELD, self._INTERNAL_CONFIG, self._logger)

        expected_messages = [
            {"id": 1, "partition": 1},
            {"id": 2, "partition": 1},
            {"id": 3, "partition": 2},
            {"id": 4, "partition": 2},
        ]

        self._verify_output_messages(all_messages, expected_messages)
        assert self._queue.empty()
