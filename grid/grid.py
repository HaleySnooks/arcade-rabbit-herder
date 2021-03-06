import numpy as np
import math
from scipy.spatial import KDTree
from typing import Tuple
from warnings import warn


class Grid:
    
    def __init__(self, x_max, y_max, tile_size, number_of_layers = 3, flip_x = False, flip_y = False):
        """
        Initiaise a grid
        :param x_max:
        :param y_max:
        :param tile_size:
        :param flip_x:
        :param flip_y:
        """

        self.max_rows = y_max
        self.max_columns = x_max

        # generate the indicies for our grid size
        # the indicies are the positions of our grid
        y_mesh, x_mesh = np.indices((y_max, x_max))

        x_mesh = x_mesh + 1
        y_mesh = y_mesh + 1

        if flip_x:
            x_mesh = np.flip(x_mesh)
        if flip_y:
            y_mesh = np.flip(y_mesh)

        # we want to store the center value in pixels for
        # our tiles
        self.tile_size = tile_size
        self.half_tile_size = (self.tile_size / 2.0)
        
        self.x_mesh = (x_mesh * self.tile_size) - self.half_tile_size
        self.y_mesh = (y_mesh * self.tile_size) - self.half_tile_size
        
        # let's persist center positions
        pixel_center_positions = np.squeeze(np.dstack([self.y_mesh.ravel(), self.x_mesh.ravel()]))
        
        # property `map_pixel_center_positions` is for assisting human lookups of the grid
        self.map_pixel_center_positions = np.squeeze(np.reshape(pixel_center_positions, (y_max, x_max, 2)))
        
        self.max_x = np.max(self.x_mesh)
        self.max_y = np.max(self.y_mesh)
        
        # property `flat_pixel_positions` is for assisting computer lookup of the grid and
        # reverse lookups for pixels to positions
        flat_pixel_positions = pixel_center_positions.flatten()
        self.flat_pixel_positions = np.reshape(flat_pixel_positions, (int(len(flat_pixel_positions) / 2), -1))

        # to find a position based on pixel position we'll use the scipy.spatial.KDTree data type
        self.tree = KDTree(self.flat_pixel_positions)

        # for data storage in our grid - initialised to 0s
        # TODO: how to handle many things at a grid position?
        # perhaps a dictionary?
        self.number_of_layers = number_of_layers
        self.data = np.reshape(np.zeros((y_max * x_max) * number_of_layers), (number_of_layers, (y_max * x_max)))

        # let's keep the last row, column values to minimise repeated lookups
        self.last_x = None
        self.last_y = None
        
        # let's keep the last x and y distances
        self.last_x_distances = None
        self.last_y_distances = None
    
    def __getitem__(self, item: Tuple[int, int]):
        """
        Get the data stored nearest to x, y
        :param item: Tuple[int, int, int]
        :return:
        """
        x = item[0]
        y = item[1]

        # query_result[0] - The distances to the nearest neighbour
        # query_result[1] - The locations of the neighbours
        query_result = self.query_tree(x, y, k =1, distance_upper_bound = self.tile_size)
        
        if not query_result:
            raise ValueError(f"Pixel positions not found in grid! {x}, {y}")

        result = []
        for i in range(0, self.number_of_layers):
            result.append(self.data[i][query_result[1]])

        return np.array(result).flatten()
    
    def __setitem__(self, key: Tuple[int, int, int], value):
        """
        Set the data stored nearest to x, y
        :param key:
        :param value:
        :return:
        """
        layer = 0

        x = key[0]
        y = key[1]
        if len(key) > 2:
            layer = key[2]

        query_result = self.query_tree(x, y)
        
        if not query_result:
            raise ValueError(f"Pixel positions not found in grid! {x}, {y}")

        # query_result[0] - The distances to the nearest neighbour
        # query_result[1] - The locations of the neighbours        
        self.data[layer][query_result[1]] = value
        return
    
    def __sub__(self, item):
        """
        Remove all occurances of an item from the data layer
        :param item:
        :return:
        """
        matches = np.where(self.data == item)
        if len(matches[0]) > 0:
            try:
                assert(len(matches[0]) == 1)
                assert(len(matches[1]) == 1)
            except AssertionError as e:
                print("There can be only one result in any layers")
                raise e

            self.data[matches[0][0]][matches[1][0]] = 0.0
        
    def __add__(self, other: Tuple[int, int, int], layer = 0):
        """
        Add to data layer, expected to be a Tuple
        :param other: (data_to_be_addded, at_x, at_y)
        :return:
        """
        self.__setitem__((other[1], other[2], layer), other[0])
    
    def convert_position_to_pixels(self, row, column):
        """
        Convert a row, column to y, x (respective) values
        :param row:
        :param column:
        :return:
        """
        x = (column + 1) * self.half_tile_size
        y = (row + 1) * self.half_tile_size
        return x, y
    
    def get_pixel_center(self, row, column):
        """
        Get the pixel enter of a given grid position
        :param row:
        :param column:
        :return:
        """
        result = self.map_pixel_center_positions[row][column]
        return result[1], result[0]
    
    def get_column_row_for_pixels(self, x, y):
        """
        Get the column, row for a given x, y
        :param x:
        :param y:
        :return:
        """
        # get the center values for the x,y
        center_x, center_y = self.get_pos_for_pixels(x, y)
        
        # find the intersection of the x and y values in our grid returns and array of array of array of bool
        match = (self.map_pixel_center_positions[:, :, 1] == center_x) & \
                (self.map_pixel_center_positions[:, :, 0] == center_y)
        
        # be we need the indexes
        result_index = np.where(match)

        # this assmues there is a match and only one match :/
        # TODO: handle != 1 match
        row = result_index[0]
        column = result_index[1]
        
        if len(row) > 0 and len(column) > 0:
            return row[0], column[0]
        else:
            print(f"cannot find xy: {x},{y} in grid")
            return None, None

    def grid_for_pathing(self):
        """
        return the 0 layer grid which is expected to contain the solid and non-solid tiles for
        pathing, where > 0 means a solid tile.
        :return:
        """
        # Note the order of rows then columns
        path_grid = np.reshape(self.data[0], (self.max_rows, self.max_columns))
        
        return path_grid
    
    def get_pos_for_pixels(self, x, y):
        """
        Reverse lookup for grid pixel centre based on given x,y position
        :param x:
        :param y:
        :return:
        """
        query_result = self.query_tree(x, y)
        if not query_result:
            raise ValueError(f"Pixel positions not found in grid! {x}, {y}")
        
        # query_result[0] - The distances to the nearest neighbour
        # query_result[1] - The locations of the neighbours
        yx = self.flat_pixel_positions[query_result[1]]
        return yx[1], yx[0]
    
    def query_tree(self, x, y, k = 1, distance_upper_bound = np.inf):
        """
        Get the data in our grid at the specified pixel position
        :param x:
        :param y:
        :param k: (optional) The number of nearest neighbors to return.
        :param distance_upper_bound: What's the maximum distance we're willing to consider as neighbours
        :return:
        """
        # query_result[0] - The distances to the nearest neighbour
        # query_result[1] - The index locations of the neighbours
        query_result = self.tree.query([y, x], k = k, distance_upper_bound = distance_upper_bound)
        return query_result
    
    def query(self, x, y, k = 1, distance_upper_bound = np.inf):
        query_result = self.query_tree(x, y, k = k, distance_upper_bound = distance_upper_bound)

        if k == 1:
            # if only searching for one neighbour, then lets convert to a tuple of two
            # numpy arrays as "d has shape tuple if k is one, or tuple+(k,) if k is larger than one"
            # https://docs.scipy.org/doc/scipy-0.14.0/reference/generated/scipy.spatial.KDTree.query.html
            query_result = (np.array([query_result[0]]), np.array([query_result[1]]),)

        if query_result:
            try:

                # filter out infinity
                index_valid = np.where(query_result[0] < np.inf)[0]

                # then get the indexes in our data that are < np.inf
                entity_valid_indexes = query_result[1][index_valid]

                # then for every layer get the values at the entity_valid_indexes using
                # numpy array slicing and dicinng and no loops
                entity_ids = self.data[0:self.number_of_layers, entity_valid_indexes]

                # the distances we have are for 1 dimenions, expand so that
                # we have as dimension results for each valid index * number of layers
                distances = np.broadcast_to(
                    query_result[0],
                    (self.number_of_layers, len(query_result[0]))
                ).T

                # returning into a flattened array so that we there's only
                # one result we still have an array
                return list(zip(
                    np.array(entity_ids).flatten(),
                    np.array(distances).flatten()
                ))
            except IndexError as e:
                print(e)
                warning_message = f"IndexError Grid.query({x}, {y}, {k}, {distance_upper_bound})"
                warn(warning_message)
                pass

        return None, None       
    
    def get_x_y_distances(self, x, y):
        """
        Get the distances for rows and columns from the given x, y pixel point.
        Used mostly by other distance calculation functions.

        :param x:
        :param y:
        :return:
        """
        if x == self.last_x:
            x_distances = self.last_x_distances
        else:
            self.last_x = x
            self.last_x_distances = self.flat_pixel_positions[:, 1] - x
            x_distances = self.last_x_distances
        
        if y == self.last_y:
            y_distances = self.last_y_distances
        else:
            self.last_y = y
            self.last_y_distances = self.flat_pixel_positions[:, 0] - y
            y_distances = self.last_y_distances
        
        return y_distances, x_distances
    
    def get_row_column_distances(self, row, column):
        """
        Get the distances for rows and columns from the given row, column.
        Used mostly by other distance calculation functions.
        :param row:
        :param column:
        :return:
        """
        y, x = self.get_pixel_center(row, column)
        return self.get_x_y_distances(x, y)
    
    def get_straight_line_distances(self, row, column):
        """
        Get the straight line distance from the center of the given row, column
        to all other centers in the grid.
        :param row:
        :param column:
        :return:
        """
        row_distances, column_distances = self.get_row_column_distances(row, column)
        return np.sqrt((column_distances * column_distances) + (row_distances * row_distances))
    
    def get_straight_line_distance_between_rows_columns(self, start_row, start_column, end_row, end_column):
        """
        Get the straight line distance between two grid positions centers.
        :param start_row:
        :param start_column:
        :param end_row:
        :param end_column:
        :return:
        """
        start_pixels = self.get_pixel_center(start_row, start_column)
        end_pixels = self.get_pixel_center(end_row, end_column)
        return self.get_straight_line_distances_between_pixels(start_pixels, end_pixels[1])
    
    @staticmethod
    def get_straight_line_distances_between_pixels(start_xy, end_xy):
        """
        Get straight line distances between two xy pairs
        :param start_xy:
        :param end_xy:
        :return:
        """
        x = (start_xy[0] - end_xy[0])
        y = (start_xy[1] - end_xy[1])
        return math.sqrt(x**2 + y**2)
    
    def get_angles(self, row, column, origin_angle):
        """
        Get the direction in degrees from the center of the given row, column
        to all other centers in the grid.
        :param row:
        :param column:
        :param origin_angle:
        :return:
        """
        row_distances, column_distances = self.get_row_column_distances(row, column)
        result = origin_angle - np.degrees(np.arctan2(row_distances, column_distances) % (2 * np.pi))
        result[np.where(result < 0)] += 360
        result[np.where(result >= 360)] -= 360
        return result
    
    def get_positions_in_fov(self, row, column, origin_angle, fov, tile_distance):
        """
        Get an indexer for grid positions that in the field of view
        from the center of the given row, column
        :param row:
        :param column:
        :param fov:
        :param origin_angle:
        :param tile_distance:
        :return:
        """
        straight_line_distances = self.get_straight_line_distances(row, column)
        theta = self.get_angles(row, column, origin_angle)
        half_fov = fov / 2
        
        return np.logical_and(
            np.logical_or(theta >= (360 - half_fov), theta <= half_fov),
            straight_line_distances < (self.half_tile_size * tile_distance) - self.half_tile_size
        )
