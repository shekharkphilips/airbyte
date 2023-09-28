#
# Copyright (c) 2023 Airbyte, Inc., all rights reserved.
#
from queue import Queue

from airbyte_cdk.sources.streams.concurrent.partitions.partition import Partition
from airbyte_cdk.sources.streams.concurrent.partitions.types import PartitionCompleteSentinel, QueueItem


class PartitionReader:
    """
    Generates records from a partition and puts them in a queuea.
    """

    def __init__(self, queue: Queue[QueueItem]) -> None:
        """
        :param queue: The queue to put the records in.
        """
        self._output_queue = queue

    def process_partition(self, partition: Partition) -> None:
        """
        Process a partition and put the records in the output queue.
        When all the partitions are added to the queue, a sentinel is added to the queue to indicate that all the partitions have been generated.

        This method is meant to be called from a thread.
        :param partition: The partition to read data from
        :return: None
        """
        for record in partition.read():
            self._output_queue.put(record)
        self._output_queue.put(PartitionCompleteSentinel(partition))